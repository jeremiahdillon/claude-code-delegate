---
name: delegate
description: Delegate bounded inference or agent work to cheap commodity models (OpenRouter open-weight models, Google Gemini) via delegate-inference (one-shot over known files) or delegate-agent (headless OpenCode agent that searches, reviews, or makes mechanical edits). Use when the user has approved delegation this session and a task is bulk summarization, extraction, first-pass or adversarial review, repo/system discovery, or repetitive file edits. Always confirm with the user once per session before the first delegated call.
---

# Delegating to commodity models

Two CLIs on PATH. Their config (`models.json`, `deny.txt`) sits in the tool's directory; `delegate-inference --list-models` prints its path.

| Tool | Use when | Mechanism |
|---|---|---|
| `delegate-inference` | You already know the exact files/text to process. Single turn, no tools. | Direct API call (OpenRouter with zero-data-retention, or Google AI Studio) |
| `delegate-agent` | Files must be discovered, or the task needs multi-step tool use (grep, reading around, running read-only commands), or mechanical edits. | Headless `opencode run --auto`. If an OpenCode server is configured, it attaches so the user can watch in the web UI |

Both write the result to disk and print one line: `DONE: <path>  model=… cost=$… time=…s`. Nothing large comes back on stdout.

## Consent (required)

Delegation spends the user's OpenRouter/Google credits and sends content to third-party providers. **Before the first delegated call in a session, ask the user and get a yes.** Say which tier, which model, roughly what is sent, and the expected cost. After that, keep using it for the kinds of task they approved; ask again for anything materially different (for example build mode, a pricier model, or sending a new category of material). Never call these tools from inside another automation the user did not ask for.

## When delegation fits, and when it does not

Good fits:
- Digesting large documents, logs, transcripts or many files into notes you then read selectively.
- First-pass or adversarial review: a second model looking for problems in a diff, spec or design.
- Discovery: "find where X is configured on this machine / in this repo and explain it."
- Mechanical, easily verified edits: renames, reorganizing files, repetitive find-and-replace.

Poor fits: final judgment calls, anything where a subtle miss is costly, security-sensitive decisions, or synthesis the user will rely on without you checking it. Cheap models are often much faster and cheaper on bulk extraction, but they can miss the single most important fact and add noise. **Treat worker output as a lead to verify, not as ground truth.** You remain responsible for the synthesis.

## Choosing a model

`delegate-inference --list-models` shows the roster from `models.json`. The shipped defaults (checked 2026-09) are:

- `default`: `deepseek/deepseek-v4.1-flash`. Fast (about 237 tok/s), strongest cheap model on agentic and long-context work. Start here.
- `value`: `z-ai/glm-5.3-flash`. Scores higher on intelligence at about half the price, but about 5x slower. Good for big background batches.
- `smart`: `xiaomi/mimo-v2.6-pro`. Top intelligence score at a flash-tier price, but slow and served by a single ZDR provider. Use for hard reasoning or careful review.
- `strong`: `z-ai/glm-5.3`. About 10x the price. Use when quality matters and `smart` is unavailable.
- `gemini`: `gemini-3.8-flash` (Google direct). Very fast, multimodal, a second opinion from a different lab. **Not ZDR.**
- `lite`: `gemini-3.5-flash-lite` (Google direct). Trivial bulk classification or tagging. **Not ZDR.**

If the default is a poor fit (for example heavy math, polished writing, image/PDF input, or very large jobs), suggest a better alias to the user, or a full model id (`vendor/model` means OpenRouter; `gemini-*` means Google). Rankings go stale: when a model is superseded, update `models.json` (its `updated` and `source` fields record when and from where).

Privacy: OpenRouter calls always send `zdr: true` and `data_collection: deny`. A model with no ZDR endpoint fails with exit 6 ("no zero-retention endpoint"), so do not work around that. Google AI Studio direct is **not** zero-retention (paid-tier prompts are not used for training, but are retained for abuse monitoring). Prefer an OpenRouter alias for anything sensitive.

## delegate-inference

```bash
delegate-inference --files a.md b.md --prompt "Summarize the design decisions and open questions"
git diff main...HEAD | delegate-inference --files - --prompt-file ~/prompts/review.md --model smart
delegate-inference --files transcript.txt --prompt "..." --dry-run    # plan, token count and cost; sends nothing
```
Flags: `--prompt | --prompt-file`, `--files` (`-` = stdin; the shell expands globs), `--model`, `--out`, `--bare`, `--max-cost` (default $0.50), `--max-tokens`, `--reasoning off|low|medium|high`, `--json`, `--chunk`, `--dry-run`.

- It checks the OpenRouter key balance first, and refuses if the estimate exceeds `--max-cost`.
- If the input exceeds the model's context it **refuses** (exit 8) and tells you the size. Then either trim the input, pick a larger-context model, or pass `--chunk`. `--chunk` maps over chunks and merges the results, which can lose cross-chunk connections, so use it knowingly.

## delegate-agent

```bash
delegate-agent --prompt "Find where retries and timeouts are configured and explain them" --dir ~/code/service
delegate-agent --mode build --dir ~/code/site --prompt "Rename all *.jpeg under assets/ to *.jpg and update references"
delegate-agent --prompt-file BRIEF.md --out _review/cycles/c1/iter-01/review.md --bare --model smart
```
Flags: `--prompt | --prompt-file`, `--mode plan|build` (default plan), `--dir` (default cwd; refuses `$HOME` and `/`), `--files` (attached as starting context), `--model`, `--out`, `--bare`, `--max-cost` (default $0.50; the run is aborted when it is exceeded), `--timeout` (minutes, default 20), `--session ID` (continue a session), `--title`, `--standalone`, `--allow-dirty`, `--allow-no-git`, `--dry-run`.

- **plan**: OpenCode's stock plan agent. File edits are blocked, but **bash is not**, and `--auto` approves reads outside `--dir`. So plan means "not intended to modify", not a sandbox.
- **build**: may create, edit and move files. In a git repo the tree must be clean at start (so changes arrive as a reviewable diff). Outside git it needs `--allow-no-git`: **ask the user first**, because there is no undo. The wrapper records every changed file and prints the list. **Review the diff before building on it**, and do not commit on the user's behalf without the usual confirmation.
- The agent is told not to install packages or rewrite git history. If a task needs a dependency, install it yourself (through your usual guarded install path) before delegating.
- With a server configured, runs appear in the OpenCode web UI titled `delegate: …`. If the server is down the wrapper runs standalone and warns.
- Cost note: every agent step carries OpenCode's large system prompt (about 15k tokens). DeepSeek caches this cheaply (about $0.002 for a short task); Gemini through OpenCode cost about 15x more for the same small task. Prefer `default` for agent work.

## Handoff protocol

1. Get consent (above). Use `--dry-run` if cost or size is uncertain.
2. Run the tool. If you want to keep working, run it in the background.
3. **Check the exit code.** 0 means success, and the `DONE:` line gives the path.
4. Read only what you need: the front matter plus the `## Executive summary` section (for example `sed -n '1,/^## [^E]/p' <path>`). Open the detail sections only for the points you act on. Do not paste the whole file into context.
5. Verify important claims yourself (the files cited, the diff) before relying on them or reporting them to the user.
6. Mention the spend when you report back (`delegate-spend` summarizes it; the ledger is `~/.claude/delegate/ledger.jsonl`).

## Output location

Default: `<git root or cwd>/.delegate/<timestamp>-<slug>.md`. `.delegate/` is added to the repo's local `.git/info/exclude` (it is never committed, and `.gitignore` is not touched). These files are transient scratch output.

`--out PATH` writes anywhere instead, for example a review protocol's `iter-NN/review.md`. `--bare` drops the front matter and the house "Executive summary" format, so the file is exactly the model's text. Use it when the prompt defines its own required format. Run metadata still goes to the ledger. The `adversarial-review` skill (`review-loop`) drives `delegate-agent --out … --bare` this way; this skill stays generic.

## Exit codes (both tools)

| Code | Meaning | What to do |
|---|---|---|
| 0 | ok | read the output |
| 2 | usage | fix the arguments |
| 3 | refused | deny-listed file, unsafe `--dir`, or a dirty/non-git tree in build mode; do not bypass without the user |
| 4 | out of credits / key limit (402) | tell the user; they top up at openrouter.ai/settings/keys (or Google AI Studio billing) |
| 5 | bad or missing key | `delegate-inference` reads `OPENROUTER_API_KEY` / `GEMINI_API_KEY` from the environment; `delegate-agent` uses OpenCode's own provider credentials (`opencode auth login`). Tell the user which one failed |
| 6 | upstream error / rate limit after retries / no ZDR endpoint | retry later or pick another model |
| 7 | agent timeout | narrow the task or raise `--timeout` |
| 8 | over `--max-cost`, or input too large | trim the input, `--chunk`, or ask the user about a higher cap |

On failure, report it to the user plainly. Do not silently redo the delegated work yourself at Claude cost without saying so.

## Deny list

`deny.txt` (next to `models.json`) holds glob patterns for files never sent via `--files` (env files, keys, credential stores). Add patterns there when the user names new sensitive material. It does **not** stop an OpenCode agent from opening files on its own, so do not point `delegate-agent` at directories holding secrets.

## Maintenance

- Model aliases, defaults, limits and the optional OpenCode server: `models.json`.
- An OpenCode model must be in `provider.openrouter.whitelist` and `.models` in `~/.config/opencode/opencode.json`. The wrapper exits 2 with instructions if it is missing. After editing, restart your OpenCode server if you run one (check nothing is mid-run first).
- The OpenCode ZDR setting is `provider.openrouter.options.extraBody.provider` in that same file.
