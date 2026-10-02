# claude-code-delegate

Let [Claude Code](https://claude.com/claude-code) hand bounded work to cheap
commodity models (open-weight models via OpenRouter, or Google Gemini), and run
automated adversarial review loops with a second model from another lab. The
review loop covers code and plans, and also writing, analyses, calculations and
research write-ups, in common document formats.

Claude stays the orchestrator. Workers write their results to disk, and Claude
reads only the summary, which keeps its context and your Claude quota for the
work that needs it.

| Component | What it does |
|---|---|
| `delegate-inference` | One-shot inference over files you already know, including documents (docx, xlsx, pdf, …; see below). Uses OpenRouter with zero-data-retention forced on, or Google AI Studio. Checks cost before spending, and refuses files whose names match its deny list (it matches paths, not file contents). |
| `delegate-extract` | Renders documents as text: what `delegate-inference` and `review-loop` use for binary formats. |
| `delegate-agent` | A headless [OpenCode](https://opencode.ai) agent (`plan` or `build` mode) for discovery, review, or mechanical edits. Has a timeout, a cost cap, and a change list for build mode. |
| `delegate-spend` | Summarizes the spend ledger. |
| `review-loop` | Automated builder/reviewer adversarial review cycles. Claude builds; a delegated model reviews each round in a fresh session, through one or more review lenses; the loop runs to convergence with a git commit at every hand-over, and the close report summarizes each round's findings and cost. |
| `skills/delegate`, `skills/adversarial-review` | Claude Code skills that teach Claude when and how to use the above. |

Everything is Python 3.9+ standard library. There are no dependencies to install.
Some document formats use tools already on the machine (see Supported formats).

---

## ⚠️ Security: read this before using `delegate-agent` or `review-loop`

`delegate-agent` runs OpenCode **with `--auto`**, which auto-approves any
permission OpenCode would otherwise ask about, using OpenCode's **stock** `plan`
and `build` agents:

- **`plan` mode is not a sandbox.** File *edits* are blocked, but the agent can
  still run shell commands, and `--auto` lets it read files **outside** the
  target directory. That includes your home directory, SSH keys, cloud
  credentials, and wherever you keep API keys.
- **Prompt injection is the realistic threat.** If you point the agent (or a
  `review-loop` reviewer) at content you don't control, that content can contain
  instructions. A malicious README, code comment, issue text or document could
  tell the agent to read your secrets and send them somewhere, and `--auto`
  would approve it.
- **The deny list (`delegate/deny.txt`) only covers files you pass with
  `--files`.** It does not restrict what an agent chooses to open itself.
  Out-of-scope paths in a review brief are enforced by prompt only.
- **`review-loop` rejects a round if the reviewer changed the working tree,** but
  it cannot detect reads.

Recommendations:

1. **Only point `delegate-agent` and `review-loop` at repositories and documents
   you trust.** `delegate-inference` has no tools, so it is safe to feed it
   untrusted text, though its output shouldn't be trusted.
2. For untrusted content, define locked-down OpenCode agents instead of the stock
   ones, and point `--mode` at them. `--auto` cannot override an explicit `deny`,
   so deny `external_directory`, reads of `*.env`, key files and credential
   stores, and restrict `bash` to an allowlist. See OpenCode's
   [permission docs](https://opencode.ai/docs/permissions/).
3. Keep API keys out of the directories agents work in, and prefer a
   secrets manager over plain files where you can.
4. Use separate, spend-limited API keys for delegation. OpenRouter lets you set a
   per-key credit limit.

Delegated calls also **send your content to third-party model providers.**
OpenRouter calls always request zero-data-retention endpoints
(`zdr: true`, `data_collection: deny`). **Google AI Studio direct calls are not
zero-retention**: paid-tier prompts are not used for training, but are retained
for abuse monitoring. Use the OpenRouter aliases for anything sensitive.

---

## Requirements

- Python 3.9+, `git`
- An [OpenRouter](https://openrouter.ai) API key, and optionally a Google AI Studio key
- For `delegate-agent` and `review-loop`: [OpenCode](https://opencode.ai), with
  OpenRouter (and optionally Google) configured via `opencode auth login`

## Install

```bash
git clone https://github.com/jeremiahdillon/claude-code-delegate.git ~/.local/share/claude-code-delegate
cd ~/.local/share/claude-code-delegate
./install.sh            # symlinks the CLIs into ~/.local/bin, copies the skills into ~/.claude/skills
```

`install.sh` never overwrites existing files unless you pass `--force`. Then:

1. **Keys.** Export `OPENROUTER_API_KEY` (and `GEMINI_API_KEY` for the Google
   aliases) in the environment Claude Code runs in.
2. **Zero-data-retention in OpenCode.** Add this to your OpenCode config
   (`~/.config/opencode/opencode.json`) so `delegate-agent` traffic is ZDR-only too:
   ```json
   {
     "provider": {
       "openrouter": {
         "options": { "extraBody": { "provider": { "zdr": true, "data_collection": "deny" } } }
       }
     }
   }
   ```
   Models used through OpenCode must also be available to OpenCode. If you use a
   provider `whitelist`, add the models from `delegate/models.json` to it.
3. **Consent rule.** Append `CLAUDE.md.snippet` to `~/.claude/CLAUDE.md`, so Claude
   asks you once per session before delegating anything.
4. **Optional: watch agent runs live.** If you run a persistent `opencode serve`,
   set `"opencode": {"server": "http://127.0.0.1:4096"}` in `delegate/models.json`
   (or export `DELEGATE_OPENCODE_SERVER`). Put the server's basic-auth credentials
   in `OPENCODE_SERVER_USERNAME` / `OPENCODE_SERVER_PASSWORD`, or in a `KEY=VALUE`
   file named by `"server_env_file"`. Sessions then appear in the OpenCode web UI.
5. **Check it works:** `review-loop/tests/selftest.sh` and
   `delegate/tests/extract_selftest.sh` (no API calls), then
   `delegate-inference --list-models`, `delegate-extract --formats` and a
   `--dry-run`.

## Usage

In Claude Code, just ask:

- *"Summarize these five design docs with a cheap model."* Claude confirms, runs
  `delegate-inference`, and reads back only the executive summary.
- *"Have a delegated agent find where retries are configured in this repo."*
- *"Run an adversarial review of the last three commits, use `smart` as the reviewer."*
  Claude drafts a review brief for your approval, then runs reviewer rounds,
  verifying and fixing findings, until the two converge. Records land in
  `_review/` in your repo.
- *"Adversarially review my competitive teardown in ~/Documents/teardown.docx
  against the sources in ~/Documents/sources."* Claude picks lenses
  (`analysis, research, writing`), and because the folder isn't in git, reviews
  a copy in a workspace, then offers to copy the accepted fixes back.

### Review lenses

A cycle declares one or more lenses, primary first. Each adds review
questions and finding categories. None assumes a format or convention for the
work; conventions it must follow go in the brief.

| Lens | For | Checks the work against |
|---|---|---|
| `code` | software changes | intent, edge cases, tests |
| `plan` | implementation plans, specs | the codebase as it actually is |
| `writing` | essays, memos, docs | its stated purpose and audience |
| `analysis` | teardowns, strategy or decision memos | its own evidence |
| `quantitative` | calculations, models, tax prep, spreadsheets | independent recomputation |
| `research` | claims about the world | the provided sources on disk |
| `general` | anything else | the brief's intent and checklist |

Add or override lenses per project in `<review-dir>/lenses/<name>.md`.

### Getting the work into git

The loop needs git (it diffs and commits every round). `review-loop new
--target PATH` decides how from what the target is: review in place if it's
tracked in a clean repo; otherwise, usually, copy it into a separate workspace
repo and let `review-loop apply` copy the changes back, with every write
checked against the original. It asks before anything invasive (committing
your pending work, or `git init` in your folder).

### Supported formats

| Format | How |
|---|---|
| docx, pptx, xlsx, odt, ods, odp, html | standard library (spreadsheets: each cell's cached value and formula) |
| txt, md, csv, tsv, json | as is |
| doc, rtf, webarchive | macOS `textutil` |
| pdf | macOS PDFKit (needs the Xcode Command Line Tools), else `pdftotext`, else `pypdf` |
| images, scanned PDF pages | `tesseract`, else macOS Vision (Command Line Tools) |

Layout, tracked changes, comments and charts are not kept.

Or use the CLIs directly. Each has `--help`, and the skills document every flag,
the output contract (`DONE: <path> …`), and the shared exit codes.

## Configuration

| File | Purpose |
|---|---|
| `delegate/models.json` | Model aliases (`default`, `value`, `smart`, `strong`, `gemini`, `lite`), defaults, cost/timeout limits, optional OpenCode server |
| `delegate/deny.txt` | Glob patterns for files never sent via `--files`. Add your own key locations. |
| `review-loop/defaults.json` | Reviewer model, iteration cap (5), budget per cycle ($2) and per round ($0.75), round timeout (45 min), workspace location and size cap, extraction size cap, core and legacy finding categories |
| `review-loop/templates/lenses/*.md` | The shipped review lenses |
| `<repo>/_review/config.json` | Per-project overrides for `review-loop` |

The model roster reflects price and benchmark data checked in September 2026. It
goes stale quickly, so re-check [Artificial Analysis](https://artificialanalysis.ai)
and OpenRouter's zero-retention endpoint pricing, then edit `models.json`.

Spend is logged to `~/.claude/delegate/ledger.jsonl`. Run `delegate-spend` to see it.

## Out of scope: web verification

The reviewer works only from files on disk. It does not search the web or
fetch URLs, so a `research` review checks claims against the sources you
provide and reports unsupported claims as such, not as false.

This is a deliberate boundary, and a possible extension. OpenCode has a
built-in `webfetch` tool and a `websearch` tool (enabled with
`OPENCODE_ENABLE_EXA=1`), and other search providers (Brave, Perplexity) can be
added through MCP. It was left out because:

- search providers see and may retain your queries, which reveal the content
  under review (they are not covered by OpenRouter's zero-retention setting);
- fetched pages are untrusted input to an agent running with `--auto`, which
  is the prompt-injection risk described in the Security section;
- cheap models are weak fact-checkers, so web findings would need full
  re-verification anyway.

Claude, as the builder, can still check an external claim with its own web
tools when verifying a finding, with your consent.

## License

MIT; see `LICENSE`.
