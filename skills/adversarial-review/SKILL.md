---
name: adversarial-review
description: Run an automated, iterative adversarial review of code, an implementation plan, or other work. Claude Code is the builder; a cheaper model from another lab reviews through delegate-agent, round by round, until the two converge. Use when the user asks for an adversarial review, a second-model review, a "review loop", or a critique cycle on a diff, branch, plan or document, optionally naming a reviewer model.
---

# Adversarial review loop

`review-loop` (on PATH; part of this toolkit) runs review cycles. **You are the builder.** The reviewer is a delegated model, by default `default` (DeepSeek V4.1 Flash; see `delegate-agent --list-models`). Each round runs as a fresh headless OpenCode session in `plan` mode through the `delegate` skill's `delegate-agent`. The script handles the mechanics:
- builds the reviewer's prompt from the protocol, project notes, brief, findings ledger, and the latest review, response and diff;
- runs the reviewer;
- checks the review's format, and retries it in the same session if needed;
- makes sure the reviewer changed nothing;
- tracks spend;
- commits every hand-over.

You make the judgment calls: verify each finding, fix, respond, and decide when to close.

In practice cycles tend to converge in 2–3 rounds for a few cents to tens of cents with the default reviewer. **The quality of the review follows the quality of the brief.**

## Consent and set-up (once per cycle)

A request for an adversarial review is a request to delegate, but still **confirm before `init`**. Show the user, in one message:
- the target, and the top items of the checklist;
- the reviewer model;
- the caps: 5 iterations, $2 for the cycle, $0.75 per round, and 45 minutes per round (the defaults in review-loop's `defaults.json`);
- anything you inferred for settled decisions or out-of-scope paths.

Adjust what they change.

**Preconditions:**
- **A git repository.** If there isn't one, ask before running `git init`.
- **Committed work.** The reviewer reviews committed state, and `init` refuses a dirty tree. **Ask before committing the user's work.** Don't discard anything.

## Running a cycle

1. **Scaffold.** Run `review-loop new <cycle>`, naming the cycle `YYYY-MM-DD-<topic>`.
   - The first time in a repo, this also creates `_review/` with `config.json`, `README.md` and `PROJECT.md`.
   - Records are committed by default. `--review-dir .delegate/review` (a global flag) keeps them out of git, if the user prefers.
   - Fill in `PROJECT.md`: what the project is, paths never to read, the standard checks, and commands never to run. Ask the user about sensitive paths if they aren't obvious.
2. **Write the brief** at `_review/cycles/<cycle>/BRIEF.md`. Replace every TODO; `init` checks for them.
   - `**Type:** code | plan | other`.
   - **What you are reviewing.** For code, give the exact `git diff <base>..HEAD -- <paths>`, where `<base>` is the commit before the work. For a plan, give the document paths and the codebase it must fit.
   - **Intent, settled decisions, forward references, known limitations.** Draw these from the conversation and the project's docs. Settled decisions stop the reviewer re-arguing choices the user already made. Forward references stop it reporting unbuilt things as defects.
   - **Checks the reviewer may run, and must never run.** Tests are the reviewer's best evidence.
   - **A specific checklist in priority order.** Name the functions, steps, edge cases and invariants where the risk is. A generic checklist gets a generic review. For plans, ask about feasibility against the actual code, sequencing, failure and rollback, and ambiguity.
3. **Open the cycle:**
   ```
   review-loop init <cycle> [--reviewer <alias|model>] [--max N] [--budget USD] --trailer "<your commit attribution line>"
   ```
   The trailer is added to every commit of the cycle.
4. **Run the loop.** Repeat until you close:
   1. **Run `review-loop review`** with Bash `run_in_background: true`. It can take up to 45 minutes; you're notified when it finishes. **Don't modify the repository while it runs.**
   2. **On `REVIEWED …`**, read `iter-NN/review.md` in full. For **each** `F-`, `C-`, and non-verified `V-` item, **check it yourself** before deciding: read the cited code, reproduce the failure, run the tests. The reviewer is fast, but it can be wrong or miss context.
      - **Accept** only what holds up. **Reject** with evidence. **Never accept just to end the loop**, and never reject reflexively. A high acceptance rate is fine when findings are well evidenced, but it is not a quota.
   3. **Fix what you accepted** and run the project's checks.
   4. **Write `iter-NN/response.md`** (format below).
   5. **Hand over.** Run `review-loop respond --decision continue`. It commits your fixes and the response together.
   6. **Tell the user in one line:** the round, the findings by severity, what you accepted or rejected, and the cumulative spend.
5. **Close** when the reviewer recommends `converge` and no blocker or major item is open.
   - Write `CLOSE.md` (format below).
   - Write a short `response.md` for the final round.
   - Run `review-loop respond --decision close`.
   - Then report: the outcome, what changed, **open disputes for the user to decide**, the backlog, the iteration count and the spend.

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
review-loop new <cycle>                 scaffold (and the review dir, first time)
review-loop init <cycle> [...]          open; tree must be clean
review-loop review [--model M]          one reviewer round
review-loop respond --decision continue|close [--override R]
review-loop status | ledger | list | changes [--iteration N]
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
- **Settled design choices, kept on purpose:**
  - one reviewer (no panels);
  - a fresh reviewer session each round, with everything carried forward in the prompt;
  - running to convergence without pausing between rounds.
