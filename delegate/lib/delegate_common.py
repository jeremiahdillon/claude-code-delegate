"""Shared plumbing for delegate-inference and delegate-agent.

Config lives in this file's parent's parent dir (the delegate/ directory):
  models.json  aliases -> provider/model, defaults, limits
  deny.txt     glob patterns for files that must never be sent to a model
Spend ledger: ~/.claude/delegate/ledger.jsonl

Python 3.9+ stdlib only; no dependencies.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path.home()
CONFIG_DIR = Path(__file__).resolve().parent.parent
MODELS_FILE = CONFIG_DIR / "models.json"
DENY_FILE = CONFIG_DIR / "deny.txt"
STATE_DIR = HOME / ".claude" / "delegate"
LEDGER = STATE_DIR / "ledger.jsonl"
CACHE_DIR = STATE_DIR / "cache"

# Exit codes shared by both tiers (documented in the skill).
EXIT_OK = 0
EXIT_FAIL = 1          # unexpected failure
EXIT_USAGE = 2
EXIT_REFUSED = 3       # deny-listed / secret-looking / unsafe target
EXIT_CREDITS = 4       # out of credits / quota (HTTP 402)
EXIT_AUTH = 5          # bad or missing key
EXIT_UPSTREAM = 6      # rate limit / provider error after retries
EXIT_TIMEOUT = 7
EXIT_BUDGET = 8        # over --max-cost, or input too large for the model


class DelegateError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def die(code: int, msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg: str):
    print(f"warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------- config

def load_config() -> dict:
    try:
        return json.loads(MODELS_FILE.read_text())
    except (OSError, ValueError) as e:
        die(EXIT_FAIL, f"cannot read {MODELS_FILE}: {e}")


def resolve_model(cfg: dict, name: str | None, tier: str) -> dict:
    """Alias or raw id -> {alias, provider, model, ...provider config}.

    Raw ids: 'gemini-*'/'gemma-*' (no slash) -> google; anything with a slash
    -> openrouter. Prefix 'google:' or 'openrouter:' to force a provider.
    """
    name = name or cfg["defaults"][tier]
    aliases = cfg["aliases"]
    if name in aliases:
        entry = dict(aliases[name], alias=name)
    else:
        m = re.match(r"^(openrouter|google):(.+)$", name)
        if m:
            prov, model = m.groups()
        elif "/" in name:
            prov, model = "openrouter", name
        elif name.startswith(("gemini", "gemma")):
            prov, model = "google", name
        else:
            die(EXIT_USAGE, f"unknown model or alias '{name}'. Aliases: {', '.join(aliases)}")
        entry = {"provider": prov, "model": model, "alias": None}
        # pick up price/context if a known alias points at the same model
        for a in aliases.values():
            if a["provider"] == prov and a["model"] == model:
                entry = dict(a, alias=None)
    entry["provider_cfg"] = cfg["providers"][entry["provider"]]
    return entry


def model_label(m: dict) -> str:
    return f"{m['model']}" + (f" ({m['alias']})" if m.get("alias") else "")


def list_models(cfg: dict):
    print(f"{'alias':<9} {'provider':<11} {'model':<32} note")
    for k, v in cfg["aliases"].items():
        star = "*" if k in cfg["defaults"].values() else " "
        print(f"{k + star:<9} {v['provider']:<11} {v['model']:<32} {v.get('note', '')}")
    print(f"\n* default. Config: {MODELS_FILE} (updated {cfg.get('updated', '?')})")


# ---------------------------------------------------------------- deny list

def _deny_patterns() -> list:
    pats = []
    try:
        for line in DENY_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    except OSError:
        warn(f"no deny list at {DENY_FILE}")
    return pats


def _match(path: Path, pat: str) -> bool:
    # Patterns with a slash match the absolute path ('*' spans '/', so '**'
    # works); relative ones like 'secrets/**' match that dir anywhere.
    # Patterns without a slash match the basename.
    pat = os.path.expanduser(pat)
    if "/" not in pat:
        return fnmatch.fnmatch(path.name, pat)
    if not pat.startswith("/"):
        pat = "*/" + pat
    return fnmatch.fnmatch(str(path), pat)


def denied(path: Path) -> str | None:
    """Return the matching deny pattern, or None if the file may be sent.

    Lines starting with '!' re-allow (e.g. '!.env.example').
    """
    p = path.expanduser().resolve()
    hit = None
    for pat in _deny_patterns():
        if pat.startswith("!"):
            if hit and _match(p, pat[1:]):
                hit = None
        elif _match(p, pat):
            hit = pat
    return hit


def check_files(paths: list) -> list:
    """Validate input files; raise DelegateError(EXIT_REFUSED) on deny hits."""
    out = []
    for raw in paths:
        if raw == "-":
            out.append(raw)
            continue
        p = Path(raw).expanduser()
        if not p.exists():
            raise DelegateError(EXIT_USAGE, f"no such file: {raw}")
        if p.is_dir():
            raise DelegateError(EXIT_USAGE, f"{raw} is a directory; pass files (globs are expanded by the shell)")
        pat = denied(p)
        if pat:
            raise DelegateError(EXIT_REFUSED, f"refusing to send {raw}: matches deny pattern '{pat}' in {DENY_FILE}")
        out.append(str(p))
    return out


# ---------------------------------------------------------------- output paths

def git_root(d: Path) -> Path | None:
    try:
        r = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        return Path(r.stdout.strip()) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def slugify(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:n].rstrip("-")) or "task"


def default_out(base: Path, prompt: str) -> Path:
    """<git root or base>/.delegate/<stamp>-<slug>.md, git-excluded locally."""
    root = git_root(base)
    d = (root or base) / ".delegate"
    d.mkdir(parents=True, exist_ok=True)
    if root:
        excl = root / ".git" / "info" / "exclude"
        try:
            cur = excl.read_text() if excl.exists() else ""
            if ".delegate/" not in cur.split():
                excl.parent.mkdir(parents=True, exist_ok=True)
                with excl.open("a") as f:
                    f.write(("" if cur.endswith("\n") or not cur else "\n") + ".delegate/\n")
        except OSError:
            pass
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return d / f"{stamp}-{slugify(prompt)}.md"


def prepare_out(out: str | None, base: Path, prompt: str) -> Path:
    if out:
        p = Path(out).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return default_out(base, prompt)


def _yaml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(json.dumps(str(x)) for x in v) + "]"
    return json.dumps(str(v))


def write_output(path: Path, body: str, meta: dict, bare: bool):
    if bare:
        text = body if body.endswith("\n") else body + "\n"
    else:
        fm = "\n".join(f"{k}: {_yaml_val(v)}" for k, v in meta.items() if v is not None)
        text = f"---\n{fm}\n---\n\n{body.strip()}\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


# ---------------------------------------------------------------- ledger

def ledger(entry: dict):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        entry = {"ts": _dt.datetime.now().astimezone().isoformat(timespec="seconds"), **entry}
        with LEDGER.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        warn(f"could not write ledger: {e}")


# ---------------------------------------------------------------- prompts

def read_prompt(args) -> str:
    if args.prompt and args.prompt_file:
        die(EXIT_USAGE, "use --prompt or --prompt-file, not both")
    if args.prompt_file:
        try:
            return Path(args.prompt_file).expanduser().read_text()
        except OSError as e:
            die(EXIT_USAGE, f"cannot read prompt file: {e}")
    if args.prompt:
        return args.prompt
    die(EXIT_USAGE, "a task is required: --prompt TEXT or --prompt-file PATH")


HOUSE_FORMAT = (
    "Write your deliverable as self-contained Markdown. Start with a section "
    "'## Executive summary' of at most 10 bullets giving the key findings or "
    "results, then the detail below it. Cite file paths (and line numbers where "
    "useful) for claims about files. Say plainly what you could not determine "
    "rather than guessing."
)


# ---------------------------------------------------------------- HTTP

def http_json(url: str, key: str, body: dict | None = None, timeout: int = 600,
              extra_headers: dict | None = None) -> dict:
    """POST (or GET when body is None) JSON. Raises urllib errors to caller."""
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def classify_error_text(text: str) -> int:
    t = text.lower()
    credits = ("payment required", "insufficient credits", "more credits",
               "credits exhausted", "key limit exceeded")
    auth = ("user not found", "api key", "unauthorized", "no auth",
            "permission_denied")
    if re.search(r"\b402\b", t) or any(s in t for s in credits) \
            or ("resource_exhausted" in t and "quota" in t):
        return EXIT_CREDITS
    if re.search(r"\b401\b", t) or any(s in t for s in auth):
        return EXIT_AUTH
    return EXIT_UPSTREAM


def is_zdr_miss(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in ("no allowed providers", "data policy", "zero data retention"))


ZDR_HINT = ("no zero-retention endpoint serves this model; pick another model "
            "(see --list-models)")


def openrouter_models(key: str) -> dict:
    """id -> {context, prompt_price, completion_price}; cached for a day."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "openrouter-models.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        try:
            return json.loads(cache.read_text())
        except ValueError:
            pass
    try:
        data = http_json("https://openrouter.ai/api/v1/models", key, timeout=30)["data"]
    except Exception as e:  # noqa: BLE001 - best-effort metadata
        warn(f"could not fetch OpenRouter model list ({e}); using config values")
        return {}
    out = {}
    for m in data:
        try:
            out[m["id"]] = {
                "context": m.get("context_length"),
                "input": float(m["pricing"]["prompt"]) * 1e6,
                "output": float(m["pricing"]["completion"]) * 1e6,
            }
        except (KeyError, TypeError, ValueError):
            continue
    cache.write_text(json.dumps(out))
    return out


def fmt_cost(c) -> str:
    return "?" if c is None else f"${c:.4f}"


def fmt_cap(c: float) -> str:
    return f"${c:.2f}" if c >= 0.01 else f"${c:g}"
