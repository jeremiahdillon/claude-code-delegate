# Adversarial review records

This folder is written by `review-loop` (from claude-code-delegate). Claude Code
is the builder. A cheaper model from another lab is the reviewer, run through
`delegate-agent`.

| Path | What |
|---|---|
| `config.json` | This project's settings (reviewer model, caps, budget); overrides review-loop's `defaults.json` |
| `PROJECT.md` | Standing notes the reviewer reads every cycle (never-read paths, checks) |
| `cycles/<cycle>/BRIEF.md` | What the cycle reviews, its intent and settled decisions |
| `cycles/<cycle>/STATE.json` | Written by the script only: turn, iteration, history, spend |
| `cycles/<cycle>/iter-NN/review.md` | The reviewer's findings |
| `cycles/<cycle>/iter-NN/response.md` | The builder's verdict on each finding |
| `cycles/<cycle>/iter-NN/reviewer-prompt.md` | Exactly what the reviewer was given |
| `cycles/<cycle>/CLOSE.md` | Outcome, what changed, disputes, backlog |

Every hand-over is a git commit (`review(<cycle>): …`), so each round has an
exact diff. For status, run `review-loop status`.
