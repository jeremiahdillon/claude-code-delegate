---
name: adversarial-review
description: Run an automated, iterative adversarial review of code, an implementation plan, or other work such as writing, an analysis, calculations or a research write-up (in any file format, including docx, xlsx and pdf). Claude Code is the builder; a cheaper model from another lab reviews through delegate-agent, round by round, until the two converge. Use when the user asks for an adversarial review, a second-model review, a "review loop", or a critique cycle on a diff, branch, plan, document, spreadsheet or analysis, optionally naming a reviewer model.
---

# Adversarial review loop

`review-loop` (on PATH; part of this toolkit) runs review cycles. **You are the builder.** The reviewer is a delegated model, by default `default` (DeepSeek V4.1 Flash; see `delegate-agent --list-models`). Each round runs as a fresh headless OpenCode session in `plan` mode through the `delegate` skill's `delegate-agent`. The script handles the mechanics:
- builds the reviewer's prompt from the protocol, the cycle's review lenses, project notes, brief, findings ledger, and the latest review, response and diff;
- gets the work into git: in place, or in a copied workspace (see "Setup");
- renders binary documents (docx, xlsx, pptx, pdf, images, …) as text for the reviewer;
- runs the reviewer;
- checks the review's format, and retries it in the same session if needed;
- makes sure the reviewer changed nothing;
- tracks spend;
- commits every hand-over.

You make the judgment calls: verify each finding, fix, respond, and decide when to close.

In practice cycles tend to converge in 2–3 rounds for a few cents to tens of cents with the default reviewer. **The quality of the review follows the quality of the brief.**

## Consent and set-up (once per cycle)

A request for an adversarial review is a request to delegate, but still **confirm before `init`**. Show the user, in one message:
- the target, the lenses, and the top items of the checklist;
- the setup `new` chose (in place, `git init`, or a workspace copy, and where);
- the reviewer model;
- the caps: 5 iterations, $2 for the cycle, $0.75 per round, and 45 minutes per round (the defaults in review-loop's `defaults.json`);
- anything you inferred for settled decisions or out-of-scope paths.

Adjust what they change.

**Preconditions:** the reviewer reviews committed state in a git repository, and `init` refuses a dirty tree. `new --target` works out how to get there (below). **Ask before committing the user's work, or before `git init` in their folder.** Don't discard anything.

## Lenses

A lens tells the reviewer what to check the work against and which finding categories it may use. Pick one or more, **primary first**; `review-loop lenses` lists them.

| Lens | For | Checks the work against |
|---|---|---|
| `code` | software changes | intent, edge cases, tests |
| `plan` | implementation plans, specs | the codebase as it actually is |
| `writing` | essays, memos, docs | its stated purpose and audience |
| `analysis` | teardowns, strategy or decision memos | its own evidence: do the conclusions follow? |
| `quantitative` | calculations, models, tax prep, spreadsheets | independent recomputation, traceability, reconciliation |
| `research` | claims about the world | the **provided sources on disk** (no web) |
| `general` | anything else | the brief's intent and checklist |

Combine them to fit the work: a competitive teardown is `analysis, research, writing`; a tax package is `quantitative, research`. Lenses make no assumptions about the work's format or conventions; if it must follow a convention, say so in the brief's intent. A project can add or override a lens with `<review-dir>/lenses/<name>.md`.

## Setup: getting the work into git

`review-loop new <cycle> --target PATH [--target …] [--ref PATH …] --lenses a,b` decides from what the target is, not where it lives:

| Target | Setup | Ask the user? |
|---|---|---|
| git-ignored inside a repo | workspace | no, announce it |
| spans several repos, or git and non-git | workspace | **yes** |
| tracked in one repo, clean tree | in place in that repo | no |
| in one repo, dirty tree | in place after their work is committed, or workspace | **yes** |
| not in git, a project folder, `code`/`plan` lens | `git init` in place | **yes** |
| not in git, otherwise | workspace | no, announce it |

- When `new` prints `NEEDS DECISION`, ask the user and re-run with `--setup in-place|init|workspace`.
- `new` prints `ROOT: <path>`. **Pass `--repo <root>` on every later command** (a workspace or another repo is not your cwd).
- **Workspace:** the targets are copied to `work/` and references to `ref/` in a new repo under `~/.local/share/review-loop/workspaces/` (deny-listed files are skipped and listed). Edit the copies there. After close, run `review-loop apply` (a dry run) and show the user; run `apply --yes` (plus `--include-new` / `--include-deletes` if wanted) only with their approval. `apply` refuses any file whose original changed since the copy; those conflicts are for the user.
- **References** (`--ref`) are material the reviewer reads but doesn't review: sources for `research`, input documents for `quantitative`. Outside the repo they're copied to git-ignored `.delegate/ref/<cycle>/`.
- Without `--target`, `new` works as before: the repo containing cwd, in place, nothing extracted.

**Binary documents.** At `init` and every `respond`, binary targets and references are rendered as text under `<review-dir>/extract/<path>.md` (`delegate-extract`; spreadsheets show each cell's value and formula). The reviewer reads those. When the work itself is a docx or xlsx, edit the real file (with your document skills); the rendition is regenerated at hand-over.

## Running a cycle

1. **Scaffold.** Run `review-loop new <cycle> [--target …] [--ref …] --lenses …`, naming the cycle `YYYY-MM-DD-<topic>` (see Setup).
   - The first time in a repo, this also creates `_review/` with `config.json`, `README.md` and `PROJECT.md`.
   - Records are committed by default. `--review-dir .delegate/review` (a global flag) keeps them out of git, if the user prefers.
   - Fill in `PROJECT.md`: what the project is, paths never to read, the standard checks, and commands never to run. Ask the user about sensitive paths if they aren't obvious.
2. **Write the brief** at `_review/cycles/<cycle>/BRIEF.md`. Replace every TODO; `init` checks for them.
   - `**Lenses:**` is pre-filled from `--lenses`. (Old briefs with `**Type:** code|plan|other` still work.)
   - **What you are reviewing.** For code, give the exact `git diff <base>..HEAD -- <paths>`, where `<base>` is the commit before the work. For a plan, give the document paths and the codebase it must fit. For a document, give its paths, purpose and audience, and list reference material separately.
   - **Intent, settled decisions, forward references, known limitations.** Draw these from the conversation and the project's docs. Settled decisions stop the reviewer re-arguing choices the user already made. Forward references stop it reporting unbuilt things as defects.
   - **Checks the reviewer may run, and must never run.** Tests are the reviewer's best evidence; for `quantitative` work, a script that recomputes the totals plays the same role.
   - **A specific checklist in priority order.** Name the functions, steps, edge cases and invariants where the risk is. A generic checklist gets a generic review. For plans, ask about feasibility against the actual code, sequencing, failure and rollback, and ambiguity.
3. **Open the cycle:**
   ```
   review-loop init <cycle> [--reviewer <alias|model>] [--max N] [--budget USD] --trailer "<your commit attribution line>"
   ```
   The trailer is added to every commit of the cycle.
4. **Run the loop.** Repeat until you close:
   1. **Run `review-loop review`** with Bash `run_in_background: true`. It can take up to 45 minutes; you're notified when it finishes. **Don't modify the repository while it runs.**
   2. **On `REVIEWED …`**, read `iter-NN/review.md` in full. For **each** `F-`, `C-`, and non-verified `V-` item, **check it yourself** before deciding. The reviewer is fast, but it can be wrong or miss context. How you check depends on the lens:
      - code and plans: read the cited code, reproduce the failure, run the tests;
      - `quantitative`: recompute the figure yourself;
      - `research`: open the cited provided source and read the passage. With the user's OK you may also check an external claim with your own web tools; the reviewer never uses the web;
      - `writing` and `analysis`: read the quoted passage in context and judge. Say why in the response.
      - **Accept** only what holds up. **Reject** with evidence. **Never accept just to end the loop**, and never reject reflexively. A high acceptance rate is fine when findings are well evidenced, but it is not a quota.
   3. **Fix what you accepted** and run the project's checks.
   4. **Write `iter-NN/response.md`** (format below).
   5. **Hand over.** Run `review-loop respond --decision continue`. It commits your fixes and the response together.
   6. **Tell the user in one line:** the round, the findings by severity, what you accepted or rejected, and the cumulative spend.
5. **Close** when the reviewer recommends `converge` and no blocker or major item is open.
   - Write `CLOSE.md` (format below).
   - Write a short `response.md` for the final round.
   - Run `review-loop respond --decision close`.
   - `respond --decision close` appends a **round summary** to `CLOSE.md` (per round: findings by severity, fixes verified, your verdicts, the recommendation and the cost) and prints it. `review-loop status` shows the same table at any time.
   - Then report: the outcome, the round summary, what changed, **open disputes for the user to decide**, the backlog, the iteration count and the spend.
   - **Workspace cycles:** offer `review-loop apply` (above).

The script refuses a `converged` close if a blocker or major finding is unverified, or if the reviewer's last recommendation was `continue`. Use `--override "reason"` only with the user's agreement, and say why in `CLOSE.md`.

## Formats

**`response.md`.** You need a verdict for **every** `F-` and `C-` item in the review, and for every finding a `V-` item marks `not-fixed`, `regressed` or `partially-fixed` (answer those under the original `F-` id):
```markdown
# Response — <cycle> — iteration NN

## Summary
<what changed, checks run, continue or close>

### F-NN-01 · ACCEPT
- **Verified:** how you confirmed it (reproduced / read / test)
- **Change:** `file` — what changed (the commit holds the diff)

### F-NN-02 · REJECT
- **Reasoning:** why it is wrong or out of scope, with evidence

### F-NN-03 · PARTIAL
- **Reasoning:** … **Change:** …

### F-NN-04 · BACKLOG
- **Reasoning:** minor or nit; deferred to CLOSE.md's backlog
```
The verdicts:
- **ACCEPT:** fixed in this hand-over.
- **REJECT:** not valid, with the reasons.
- **PARTIAL:** part of it fixed.
- **BACKLOG:** valid, but minor or a nit, so deferred.

Minor and nit findings can go to the backlog instead of keeping the loop going.

**Disputes.** When you reject a finding, the reviewer may challenge it once (`C-`) with a new argument. If you reject the challenge too, it becomes a **dispute**. Stop arguing it and list it in `CLOSE.md` for the user.

**`CLOSE.md`:**
```markdown
# Close — <cycle>

Outcome: converged | cap-reached | budget-reached | aborted
Iterations: N · Findings: X (accepted A, partial P, rejected R, backlog B)

## What changed
## Open disputes (for the user to decide)
## Backlog (minor and nit, deferred)
## Notes for the next cycle
```

## When something goes wrong: report it plainly and let the user decide

| Exit | What happened | What to do |
|---|---|---|
| 3 | The tree was dirty before the round, or the reviewer changed files | Show the list. Restore only those paths after checking them; don't use a blanket reset. Then retry. |
| 4 / 5 | Out of credits or key limit / bad key (the reviewer uses OpenCode's provider credentials; see `opencode auth login`) | Tell the user. The cycle stays open, so resume with `review-loop review` once it's fixed. |
| 6 / 7 | Provider error or rate limit / the round timed out | Retry once. Then suggest `--model <alias>` or a longer timeout (`review-loop adjust --timeout 60`). |
| 8 | The cycle budget is spent, or the iteration cap was reached | Tell the user what's still open. With their approval, run `review-loop adjust --budget N` or `--max N`. Otherwise close with `Outcome: budget-reached` or `cap-reached`. |
| 9 | The review was still malformed after retries | The raw output is in `review.md`. Retry, or try another model. |

A failed round never flips the turn, and it leaves the cycle resumable.
- **To stop early,** write `CLOSE.md` with `Outcome: aborted` (or `budget-reached`) and run `review-loop respond --decision close`. This works on either turn.
- **Never quietly do the review yourself** in place of the reviewer.

## Commands

```
review-loop new <cycle> [--target P …] [--ref P …] --lenses a,b [--setup auto|in-place|init|workspace]
                                        scaffold; choose the setup; prints ROOT: for --repo
review-loop init <cycle> [...]          open; tree must be clean
review-loop review [--model M]          one reviewer round
review-loop respond --decision continue|close [--override R]
review-loop status | ledger | list | lenses | changes [--iteration N]
review-loop apply [--yes] [--include-new] [--include-deletes]   workspace cycles only
review-loop adjust [--budget USD] [--max N] [--model M] [--round-budget USD] [--timeout MIN]
```

Useful facts:
- `iter-NN/reviewer-prompt.md` records exactly what the reviewer saw.
- `review-loop ledger` lists every finding's status: open, fix-pending, verified, reopened, rejected, backlog or disputed.
- If an OpenCode server is configured for `delegate-agent`, reviewer sessions appear in its web UI titled `review: <cycle> iter NN`.
- Spend also appears in `delegate-spend`.

## Limits

- **Reviewer access.** The reviewer uses OpenCode's stock `plan` agent with `--auto`. It can't edit files, but it can run shell commands and read outside the repo. The never-read paths are enforced by prompt only, so keep secrets out of the reviewer's reach.
- **What the post-round check catches.** It catches edits in the working tree, not reads.
- **No web.** The reviewer works only from files on disk. Web verification is a possible extension, deliberately left out: search providers retain queries, fetched pages can carry prompt injection into an auto-approving agent, and cheap models fact-check poorly.
- **Extraction fidelity.** Renditions drop layout, tracked changes, comments and charts; scanned pages depend on OCR.
- **Settled design choices, kept on purpose:**
  - one reviewer (no panels);
  - a fresh reviewer session each round, with everything carried forward in the prompt;
  - running to convergence without pausing between rounds.
