# Plan: generalize review beyond code

Status: reviewed (converged, 6 rounds) · implemented · 2026-09-28

## 1. Goal

`review-loop` and the `adversarial-review` skill were built for code and
implementation plans. The loop's mechanics — brief, fresh reviewer each round,
F/V/C ledger, accept/reject with evidence, one challenge then dispute,
severity-gated convergence, caps — do not depend on the kind of work. The
code bias lives in a few thin layers: the reviewer's lens, the category list,
the evidence rule, the git precondition, and the inability to read binary
files.

This plan generalizes those layers so the same loop can review other knowledge
work produced by Claude — essays and memos, analyses such as a competitive
teardown, calculation-heavy work such as tax preparation, and research
write-ups — without assuming anything about the format or conventions of the
content under review.

## 2. Non-goals and scope boundaries

- **No web research.** The reviewer verifies only against content on disk: the
  work itself and reference material the brief puts in scope. It is not given
  web search, and the brief tells it not to fetch URLs. Claims that the
  provided material does not support are reported as "not supported by the
  provided sources", not as false. Web verification is a documented
  out-of-scope extension (see §9), noted in the README and both skills.
- **No new security hardening** (content redaction, locked-down OpenCode
  agents). The existing README guidance stands. With web research out of
  scope, the reviewer's untrusted-input exposure is unchanged from today.
- **No new dependencies.** Python 3.9 standard library plus tools that ship
  with macOS; optional use of common tools (`pdftotext`, `tesseract`, `pypdf`)
  when present.
- **No change to the loop protocol** (ID formats, verdicts, ledger states,
  convergence rules). Existing cycles and briefs keep working.

## 3. Settled decisions

1. Lenses are **combinable**; a cycle declares one or more.
2. Lens guidance and evidence rules are **format-neutral**: they ask about
   properties of the work, never about conventions it should follow. Any
   convention the work must follow is stated in the brief as intent.
3. The git setup is chosen **dynamically** from what the target is (git or
   not) and the cycle's lenses — never from a hard-coded location rule — and
   the user is asked when the choice is unclear.
4. Binary formats are handled by a new extraction tool with minimal
   dependencies.
5. Implementation happens in this repo first, with tests (§8).

## 4. Lenses

### 4.1 The set

| Lens | For | What the reviewer checks the work against | Extra categories |
|---|---|---|---|
| `code` | Software changes | Intent, behavior under edge cases, tests | security, robustness, performance, testing, privacy |
| `plan` | Implementation plans, specs | The codebase as it actually is | feasibility, sequencing, over-engineering, security, privacy |
| `writing` | Essays, memos, docs, persuasive or explanatory text | Its stated purpose and audience | argument, structure, audience, tone |
| `analysis` | Teardowns, strategy/decision memos, assessments | Its own evidence: do conclusions follow? | reasoning, evidence, alternatives, framing |
| `quantitative` | Calculations, models, estimates, tax prep, spreadsheets | Independent recomputation | calculation, assumptions, traceability, reconciliation |
| `research` | Claims about the world | The provided sources on disk | sourcing, attribution, coverage, currency |
| `general` | Anything else (today's `other`) | Intent and checklist | — |

Core categories, always allowed: `intent, correctness, completeness,
consistency, clarity, settled-risk`.

### 4.2 Lens files

Each lens is a Markdown file `review-loop/templates/lenses/<name>.md`:

```markdown
---
categories: calculation, assumptions, traceability, reconciliation
---
- Recompute every figure the work's conclusions depend on, independently, in a
  temporary directory. ...
```

- Front matter: a single `categories:` line, parsed with a regex (no YAML
  dependency). Category names must match `[a-z][a-z-]*` (the existing `F_HDR`
  pattern).
- Body: 4–8 bullets of review questions. Written as questions about properties
  (e.g. "can each figure be traced to an input?"), not conventions.
- **Project-local lenses:** a file in `<review-dir>/lenses/<name>.md` overrides
  or adds to the shipped set. Lookup order: project, then shipped.
- The `code` and `plan` lens bodies are the current text of
  `reviewer-protocol.md` §How to review step 3, moved verbatim. `general` is
  the current "Anything else" bullet.

### 4.3 Declaring lenses in the brief

- New header line: `**Lenses:** analysis, research` — primary lens first.
- Back-compat: `**Type:** code|plan|other` is still accepted and maps to
  `code`, `plan`, `general`. If both lines are present, `**Lenses:**` wins.
- `cmd_init`'s brief check (today `review-loop:306-307`, which requires
  `**Type:**`) changes to: require a `**Lenses:**` line **or** a legacy
  `**Type:**` line; the problem message names both forms.
- `cmd_init` validates that every named lens resolves to a file; otherwise it
  exits 2 listing the available lenses.
- `review-loop new <cycle> --lenses a,b` writes the `**Lenses:**` line into
  the scaffolded brief (and is required by the setup decision, §5.1). Without
  `--lenses`, the brief is scaffolded with a TODO as today.

### 4.4 Composition

- `reviewer-protocol.md` step 3 becomes a `{lenses}` placeholder.
  `build_prompt()` fills it with one `### Lens: <name>` block per lens, in the
  order declared, preceded by one sentence: "Apply every lens below; the first
  is primary. The brief's checklist sets priority across them."
- **Heading collision:** the protocol forbids `###` headings in the review, but
  the lens blocks are in the *prompt*, not the review, so `validate_review()` is
  unaffected.
- **Categories for the cycle** = core ∪ each lens's categories, deduplicated,
  in order. Computed once in `cmd_init` and stored in `STATE.json` as
  `"lenses"` and `"categories"`. A helper `cycle_categories(ctx, s)` returns
  `s.get("categories") or ctx.cfg["categories"]` (the fallback covers cycles
  opened before this change). It replaces every read of
  `ctx.cfg["categories"]`: `build_prompt()` (today line 372) and the three
  `validate_review(...)` calls in `cmd_review` (lines 449, 460, 495).
  `validate_review()` itself keeps its signature; it already takes
  `categories` as a parameter.
- **Cycles opened before this change** have no `lenses`, `targets` or `refs`
  in `STATE.json` and cannot be re-`init`ed (line 296). A companion helper
  `cycle_lenses(ctx, s)` returns `s["lenses"]` if present; otherwise it parses
  the cycle's brief — `**Lenses:**` if present, else the legacy `**Type:**`
  mapping (§4.3) — and defaults to `general` if neither parses. It is used
  by `build_prompt()`. `targets` and `refs` are read with `s.get(..., [])`
  (no extraction for old cycles, matching §6.2's no-`--target` behavior).
- `defaults.json` `categories` is kept as that fallback and renamed in docs as
  "legacy category list".
- **Legacy briefs keep today's categories.** When the lenses come from a
  legacy `**Type:**` line, the cycle's categories are the legacy category list
  ∪ the mapped lens's categories, so a `**Type:** plan` or `other` cycle can
  still file every category it can file today (e.g. `security`). Only
  `**Lenses:**` briefs get the narrower core ∪ lens sets.
- The `plan` lens also lists `security` and `privacy`, since plans can carry
  those risks.

### 4.5 Format-neutral evidence rule

`reviewer-protocol.md` "Evidence or it didn't happen" becomes:

> Every finding locates what it is about in whatever way the content allows —
> path and line, heading or section, page, sheet and cell, or a verbatim quote
> (always acceptable) — and gives the evidence: a quote, a command and its
> output, a recomputation, or a reference to the brief or a provided source.
> If a claim cannot be checked against the material provided, say so rather
> than calling it wrong. If something is an inference rather than an
> observation, say so.

## 5. Target setup (git), chosen dynamically

### 5.1 Inputs

`review-loop new <cycle> [--target PATH …] [--ref PATH …] [--lenses a,b] [--setup auto|in-place|init|workspace]`

- `--target`: the work under review (files or directories; may repeat). If
  omitted, behaves exactly as today (the git repo containing cwd, or `--repo`),
  and `--ref`/`--setup` are still allowed.
- `--lenses`: required with `--target` under `--setup auto`, because the
  decision depends on the lenses and the brief does not exist yet. The skill
  chooses lenses from the user's request before calling `new`. The value is
  also written into the brief (§4.3). The brief may still be edited before
  `init`; the only lens edit that matters to setup is one that flips row 5
  vs row 6 of §5.2 (whether the lenses include `code` or `plan`). `init` does
  **not** re-run the whole decision (after `new`, the target may now be in
  git because `new` made it so). It checks only that: if `SETUP.json` `row`
  is 5 or 6 and the brief's lenses now fall on the other side of that test,
  `init` refuses and says to re-run `new`.
- `--ref`: reference material the reviewer reads but does not review (sources
  for `research`, input documents for `quantitative`). May repeat.
- `--setup auto` (default) runs the decision in 5.2 and **prints** the
  proposal plus the reason; it only acts if the choice is unambiguous and
  non-invasive. Otherwise it exits 2 with `NEEDS DECISION: …` and the options,
  and the skill asks the user.

`Ctx.__init__` currently dies when cwd is not in git. `cmd_new` gets a
pre-Ctx path so it can run with a non-git `--target`; every other command
keeps requiring a repo.

**The review root follows the target.** For in-place setups, the root is the
target's repo — `git -C <dir> rev-parse --show-toplevel`, where `<dir>` is the
target itself if it is a directory, else its parent (`git -C` on a file
fails) — not cwd. For the init setup the root is the target directory. If `--repo` or cwd names a different repo, `new` uses the target's
repo and says so. In every setup `new` ends by printing
`ROOT: <path>` and the skill passes `--repo <root>` on every later command,
so cwd never matters after `new`.

**Two path lists, kept separate.** `new` writes the cycle's `SETUP.json`:
- `setup`, `row` (the §5.2 row number), `root`, and `lenses` (the value
  given to `new`; informational only);
- `inputs`: the `--target` and `--ref` paths **as given** (absolute), kept
  for the record and for the user's reference;
- `targets` and `refs`: the **in-tree** paths, relative to the root, where the
  reviewer reads them and extraction runs. The mapping from inputs:
  - in-place or init: `relpath(input, root)`;
  - workspace: `work/<name>` and `ref/<name>`;
  - in-place ref outside the repo: `.delegate/ref/<cycle>/<name>`.

  `<name>` is always the input's basename, with `-2`, `-3`, … appended
  before the extension on collision within the same destination directory;
  the input → in-tree mapping is recorded in `SETUP.json` (and in
  `SOURCES.json` for workspaces).

`init` copies `setup`, `targets` and `refs` into `STATE.json`. `lenses` and
`categories` in `STATE.json` are computed by `init` from the brief's validated
`**Lenses:**` (or legacy `**Type:**`) line (§4.4), never from `SETUP.json`.
`respond` uses only `STATE.json`.

### 5.2 Decision

Evaluated in order; the first matching row wins. "Target" means every
`--target` path; a single file is treated like a directory for these tests.

| # | Target | Lenses | Setup | Asks the user? |
|---|---|---|---|---|
| 1 | Any target path is git-ignored in its repo (`git check-ignore -q`) | any | **workspace** (ignored paths never show in `git status`/`git diff`, so in-place could not show changes or catch reviewer edits) | No — announced |
| 2 | Targets span several repos, or mix git and non-git | any | **workspace** | **Yes** |
| 3 | All targets in one repo, working tree clean (so every target is tracked) | any | **in-place** in that repo (today's behavior) | No |
| 4 | In one repo, dirty (including untracked target files) | any | in-place after the user's work is committed | **Yes** (as today) |
| 5 | Not in git; a single directory that looks like a project (has a manifest such as `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Makefile`) | includes `code` or `plan` | **init** (`git init` in place) | **Yes** — it changes the user's folder |
| 6 | Not in git, otherwise | any | **workspace** | No — announced in the consent message the skill already shows before `init` |
| — | No `--target` | any | today's behavior: cwd/`--repo` must be a repo | as today |

"Asks the user" means `new` exits with `NEEDS DECISION` and the skill asks;
the user's answer is passed back as `--setup`.

**Init setup (row 5), once approved:** `new` runs `git init` in the target
directory, adds `.opencode/`, `.delegate/` and every file matching `deny.txt`
to `.git/info/exclude` (listing the deny-matched files it excluded), sets the
local identity fallback as in §5.3, and commits the user's existing files as
`review(<cycle>): initial snapshot`. So `HEAD` exists and the tree is clean
when `init` runs (`cmd_init` needs both: the clean-tree check at line 318 and
`ctx.head()` at line 332).

### 5.3 Workspace mode

- Location: `<workspace_root>/<cycle>-<hash>/`, where `<hash>` is the first 8
  hex characters of the sha256 of the sorted absolute input paths, so the same
  cycle name used for different targets never collides. `workspace_root`
  comes from `defaults.json` (default
  `~/.local/share/review-loop/workspaces`), overridable per user by editing
  `defaults.json` or by `--workspace-root`.
- If the workspace directory already exists, `new` refuses (exit 2) and
  prints its path; it never reuses or overwrites a workspace.
- Layout:
  ```
  <workspace>/
    work/<basename-of-each-target>/…   editable copy of the targets
    ref/<basename-of-each-ref>/…       read-only copy of the references
    _review/                            records (normal review dir)
    SOURCES.json                        per input: original path, in-tree name, kind (file|dir);
                                        per copied file: original path, sha256; copied_at
  ```
  Names follow the §5.1 rule; the mapping is in `SOURCES.json`.
- `new` runs `git init`, sets a local `user.email`/`user.name` fallback **only
  if** none is configured globally, copies files (skipping `.git`,
  `node_modules`, `.venv`, `.DS_Store` and anything matching `deny.txt`, with
  the skipped list printed), and makes a first commit. From then on the
  workspace is an ordinary repo and every other command works unchanged.
- `new` prints the workspace path. The skill passes `--repo <workspace>` on
  every later command. `CURRENT` works as today inside the workspace.
- Size guard: refuse (exit 3) above `workspace_max_mb` (default 200) unless
  `--force`, since the copy is committed.

### 5.4 In-place references

In in-place mode, a `--ref` outside the repo is copied to
`<root>/.delegate/ref/<cycle>/`, so the reviewer can read it without leaving
its working directory. A `--ref` inside the repo is used where it is.

Today nothing in `review-loop` excludes `.delegate/` from git: `cmd_new` adds
only `.opencode/` to `.git/info/exclude` (lines 265-271), and `respond`'s
`ctx.commit([], …)` runs `git add -A`, which would commit the copied refs.
So `cmd_new` ensures both `.opencode/` and `.delegate/` are in
`.git/info/exclude` on **every** run — the exclude write moves out of the
first-time `if not (ctx.rdir / "config.json").exists()` block (line 259),
since a repo with an existing review dir would otherwise never get it — and
before copying refs checks `git check-ignore -q .delegate/ref`; if that
fails (e.g. a negating rule in the user's `.gitignore`), it refuses with exit 3
rather than risk committing reference material.

### 5.5 Copying changes back: `review-loop apply`

- Workspace mode only. Lists files in `work/` that differ from the originals
  recorded in `SOURCES.json`.
- For each, checks the original's current sha256 against the snapshot. If the
  original changed since the copy, it is a **conflict**: `apply` refuses that
  file, prints both paths, and exits 3 after processing the rest.
- Default is dry-run (prints the plan). `--yes` performs the copy. Deleted and
  new files are listed and only applied with `--include-deletes` /
  `--include-new`.
- Destination of a new file: `<original dir>/<path within work/<name>>`.
  New files can only appear under a directory input: a single-file input is
  the file `work/<name>` itself.
- **Every write or delete is conflict-checked**, not only modifications:
  - modified file: the original's current sha256 must equal the snapshot;
  - new file: the destination must not exist (if it does, the original side
    gained a file since the copy — conflict);
  - deleted file: the original must still exist with its snapshot sha256
    (if it changed or is already gone, conflict).
  `SOURCES.json` already records a sha256 per copied file, which covers the
  modified and deleted cases; the new-file case needs only an existence check.
  Conflicts are never overridden by a flag; the user resolves them by hand.
- `apply` only touches targets (`work/`), never `ref/`.
- The skill offers `apply` after close and runs it only with the user's
  approval.

## 6. Binary formats: `delegate-extract`

### 6.1 Tool

`delegate/bin/delegate-extract PATH… [--out-dir DIR] [--stdout]` renders files
as UTF-8 Markdown/text. Standard library only, plus optional system tools.

| Format | Method | Notes |
|---|---|---|
| `.docx`, `.pptx` | zipfile + xml.etree | Paragraphs, headings (from style names), tables as pipe tables, slide numbers, speaker notes |
| `.xlsx`, `.xlsm` | zipfile + xml.etree | Per sheet: each non-empty cell as `A1 = <cached value>` plus `  ƒ <formula>` when a formula exists; shared strings resolved; sheet names. Number formats: cells whose style uses a built-in date/time format (numFmtId 14–22, 45–47) or a custom format containing date tokens are rendered as ISO dates; percentages (ids 9, 10) as `%`; everything else as the raw number with the format code appended, e.g. `1234.5 [fmt: "$#,##0.00"]`, so no information is hidden |
| `.odt`, `.ods`, `.odp` | zipfile + xml.etree | Text; ODS cells with formula and value |
| `.csv`, `.tsv`, `.txt`, `.md`, `.json` | pass-through | Encoding detected from BOM, else UTF-8 with replacement |
| `.html`, `.htm` | html.parser | Visible text, headings, links as `text (url)` |
| `.doc`, `.rtf`, `.webarchive` | macOS `textutil -convert txt -stdout` | Unsupported off macOS |
| `.pdf` | macOS with Xcode Command Line Tools: a bundled `swift` script using PDFKit (`page.string`) with page markers. Else `pdftotext -layout`. Else `pypdf` if importable | If a page yields no text, it is flagged "no text layer (scanned?)" |
| Images; PDF pages with no text | `tesseract` if on PATH, else macOS Vision via the bundled swift script, else reported unsupported | OCR output is marked as OCR |

`swift` is not part of stock macOS; `/usr/bin/swift` is a shim that, without
the Command Line Tools, can pop the install dialog. So the extractor probes
first with `xcode-select -p` (exit 0 and the path exists) and treats failure
as "swift unavailable", never invoking the shim blind. The swift script runs
in interpreted mode (`swift script.swift`), which costs a few seconds of
compile time per invocation; to amortize it, one invocation handles all PDFs
(and all OCR pages) in a call, taking the paths as arguments.

- Exit codes follow delegate-*: 0 ok, 2 usage/unsupported, 3 deny-listed.
- The deny list (`check_files`) is applied to every input path before reading.
- Output header per file: `<!-- extracted from <path> by delegate-extract (<method>) -->`.

### 6.2 Uses

- **delegate-inference:** `load_inputs()` currently refuses binary files. It
  will call the extractor library in-process for known binary extensions and
  for any file with a NUL byte in the first 8 KiB, and refuse only when
  extraction is unsupported. The extractor is a module
  (`delegate/lib/extract.py`) imported by both `delegate-inference` and the
  `delegate-extract` CLI.
- **review-loop:** after `new`/`init` and at each `respond`, targets and refs
  with binary formats are extracted to `<review-dir>/extract/<relative path>.md`,
  where `<relative path>` is the file's path relative to the review root
  (in-place refs copied under `.delegate/ref/` keep that prefix).
  - What to extract comes from `STATE.json` `targets` and `refs` (the
    in-tree paths, §5.1), for every setup, so `respond` knows what to
    re-extract. Directories are expanded to the files git sees under them,
    tracked or untracked-but-not-ignored (`git ls-files --cached --others
    --exclude-standard`; at `respond` the builder's new files aren't committed
    yet — found in implementation), except paths under `.delegate/` (in-place refs copied
    there are git-ignored, so `git ls-files` returns nothing): those are
    expanded by walking the directory (`os.walk`).
  - **Without `--target`, nothing is extracted** (`targets` and `refs` are
    empty), so existing code cycles behave exactly as today.
  - Size guard: files above `extract_max_mb` (`defaults.json`, default 25)
    are skipped with a warning listing them; OCR runs only on images and on
    PDF pages that have no text layer.
  - Diff ranges shown to the reviewer currently exclude the whole review dir
    (`:(exclude){rd}`). They change to exclude `{rd}/cycles` only, so changes
    to extracted text appear in the per-round diff. The same change applies in
    both places that build the range: `build_prompt()` (line 389) and
    `cmd_changes` (line 678), so the builder's `review-loop changes` shows
    what the reviewer is shown.
  - `review-loop` imports the same module in-process. To find its directory:
    resolve `shutil.which("delegate-extract")` through symlinks
    (`Path(...).resolve()`) and use `<that>/../../lib` — this works whenever
    the CLIs are symlinked onto PATH (as `install.sh` does), wherever the
    delegate tools live; if `delegate-extract` is not on PATH, fall back to
    the sibling path `review-loop/../delegate/lib`. It is added to
    `sys.path` and `extract` is imported. If neither is found, skip
    extraction and warn. There is no subprocess path.
  - When the review dir is git-ignored (e.g. `.delegate/review`), extraction
    still happens but diffs of extracted text are unavailable; known limitation.
- **Binary targets are edited as binaries.** When the work itself is a
  `.docx`/`.xlsx`, Claude edits the real file (with its document skills); the
  extract is regenerated at hand-over. Extracts are never hand-edited.

## 7. Other changes

- `BRIEF.md` template: `**Lenses:**` line with the available lenses listed in a
  comment; §2 split into "Under review" and "Reference material (read, don't
  review)"; §8 examples for non-code work (e.g. a reconciliation script the
  reviewer may run; "None" for pure writing).
- `review-loop`: "(no code changes)" → "(no changes)"; docstring and messages
  lose code-only wording; `--help` documents `--target`, `--ref`, `--setup`,
  `apply`.
- **Bug fix, git-ignored review dirs:** the skill documents
  `--review-dir .delegate/review` as the way to keep records out of git, but
  `Ctx.commit()` runs `git add -A <review-dir>`, which git refuses (exit 1) for
  an ignored path, so `init` dies. Fix: in `Ctx.commit()`, drop pathspecs that
  `git check-ignore -q` reports as ignored before calling `git add`; the
  hand-over commit then contains only the builder's changes. Selftest covers
  it.
- **Round summary in the close report.** `respond --decision close` appends
  a generated `## Round summary` section to `CLOSE.md` (between
  `<!-- round-summary:start -->` / `<!-- round-summary:end -->` markers, which
  it replaces if present), built from `STATE.json` history: one row per
  iteration with blocker/major/minor/nit counts, fixes verified (verified of
  total `V-` items), the builder's verdicts (accept/partial/reject/backlog),
  the reviewer's recommendation, and the cost (the sum of `cost_usd` over that
  iteration's `review` and `review-failed` events, so failed attempts count),
  plus a totals row. The section is written before the close commit, so it
  is part of it. `review-loop status` prints the same table.
- `reviewer-protocol.md`: a hard rule that the reviewer works only from files
  on disk and must not fetch URLs or search the web.
- `adversarial-review` skill: choosing lenses; the setup decision flow and
  when to ask; per-lens verification guidance for the builder (recompute for
  `quantitative`; open the cited provided source for `research`; judgment with
  quoted evidence for `writing`); `apply` after close; the out-of-scope note
  on web verification.
- `delegate` skill: `delegate-extract`; `delegate-inference` now accepts
  common binary formats.
- `README.md`: describe the toolkit as reviewing work in general; a
  "Supported formats" table; an "Out of scope / possible extensions" section
  covering web verification (OpenCode's built-in `webfetch`, and `websearch`
  enabled via `OPENCODE_ENABLE_EXA`; search providers such as Brave or
  Perplexity via MCP) with the reasons it was left out: provider retention,
  prompt injection through fetched pages under `--auto`, and weak
  fact-checking by cheap models.

## 8. Implementation order and testing

1. **Build, in order:**
   1. `delegate/lib/extract.py` + `delegate-extract` + `delegate-inference`
      integration.
   2. Lens files, composition, per-cycle categories.
   3. `--target`/`--ref`/`--setup`, workspace mode, `apply`.
   4. Extraction in `review-loop`.
   5. Templates, skills, README.
2. **Tests** (no API calls):
   - `review-loop/tests/selftest.sh` gains: `**Lenses:**` with two lenses
     (prompt contains both blocks in order; a category from each validates; an
     unknown category fails); legacy `**Type:**` still works; unknown lens
     fails init; setup decision for each row of the §5.2 table (including
     `NEEDS DECISION` exits); workspace creation and `SOURCES.json`; `apply`
     dry-run and `--yes`; each conflict path separately — modified file whose
     original changed, new file whose destination already exists (refused
     even with `--include-new`), deleted file whose original changed or is
     gone (refused even with `--include-deletes`); extraction refresh at
     `respond`; an old-format `STATE.json` (no `lenses`/`categories`/
     `targets`) still builds a prompt with the legacy lens and categories.
   - New `delegate/tests/extract_selftest.sh` with small fixtures generated
     at test time by Python: docx/xlsx/pptx/odt built with zipfile (since no
     library is available to write them), and a one-page PDF with a text
     layer built by a small generator that writes the objects and computes
     the xref byte offsets (no hand-typed offsets). The xlsx fixture includes
     a formula, a shared string, a date-formatted cell and a currency-formatted
     cell. On macOS the PDF test **fails** if PDFKit can't parse the fixture;
     it skips only where no PDF backend exists. OCR tests skip when neither
     `tesseract` nor Vision is available.
   - Selftest additions for review findings: a target in a git-ignored
     directory routes to workspace; a target in a repo other than cwd makes
     that repo the root; `new` adds `.delegate/` to `.git/info/exclude` and
     in-place refs are not committed by `respond`; a `**Lenses:**`-only brief
     passes `init`; `respond` re-extracts from the stored target list.
3. **One real smoke test**: a short `writing` or
   `analysis` cycle on a sample non-git document (workspace mode), default
   reviewer.

## 9. Known limitations and out-of-scope extensions

- Web verification (see §2 and §7 README).
- Extraction fidelity: complex layouts, tracked changes, comments, charts and
  embedded objects in Office files are dropped or flattened; spreadsheet
  number formats beyond dates and percentages are shown as raw number plus
  format code, not rendered; PDFs without a text layer depend on OCR quality.
- Reviewer access is unchanged: stock OpenCode `plan` agent with `--auto`; it
  can read outside its working directory. Workspace mode narrows what is in
  its working directory but does not sandbox it.
- The builder remains responsible for verifying findings; for `writing`, many
  findings are judgment calls where "verify" means checking the quoted
  passage and deciding.
