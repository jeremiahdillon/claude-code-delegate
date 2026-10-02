# Adversarial review records

This folder is written by `review-loop` (from claude-code-delegate). Claude Code
is the builder. A cheaper model from another lab is the reviewer, run through
`delegate-agent`.

| Path | What |
|---|---|
| `config.json` | This project's settings (reviewer model, caps, budget); overrides review-loop's `defaults.json` |
| `PROJECT.md` | Standing notes the reviewer reads every cycle (never-read paths, checks) |
| `lenses/<name>.md` | Optional project lenses; add to or override the shipped ones |
| `extract/<path>.md` | Text renditions of binary targets and references, refreshed at every hand-over |
| `cycles/<cycle>/BRIEF.md` | What the cycle reviews, its lenses, intent and settled decisions |
| `cycles/<cycle>/SETUP.json` | How `new --target` got the work into git: setup, original paths, in-tree paths |
| `cycles/<cycle>/STATE.json` | Written by the script only: turn, iteration, history, spend |
| `cycles/<cycle>/iter-NN/review.md` | The reviewer's findings |
| `cycles/<cycle>/iter-NN/response.md` | The builder's verdict on each finding |
| `cycles/<cycle>/iter-NN/reviewer-prompt.md` | Exactly what the reviewer was given |
| `cycles/<cycle>/CLOSE.md` | Outcome, round summary, what changed, disputes, backlog |

Every hand-over is a git commit (`review(<cycle>): …`), so each round has an
exact diff. For status and the per-round summary, run `review-loop status`.
In a workspace cycle, `SOURCES.json` at the root records where each copy came
from; `review-loop apply` copies changes back.
