#!/bin/bash
# Mechanics self-test for review-loop, using a fake reviewer (no API calls, no cost).
# Usage: review-loop/tests/selftest.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
RL="$HERE/../bin/review-loop"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export FAKE_QUEUE="$T/queue" REVIEW_LOOP_REVIEWER="python3 $HERE/fake_reviewer.py"
pass=0; fail=0
ok()   { pass=$((pass+1)); echo "  ok   $1"; }
bad()  { fail=$((fail+1)); echo "  FAIL $1"; echo "$2" | sed 's/^/       /' | head -8; }
expect() { # name expected_exit expected_substring -- command...
  local name=$1 want=$2 grep=$3; shift 4
  local out; out=$("$@" 2>&1); local rc=$?
  if [ "$rc" = "$want" ] && echo "$out" | grep -q -- "$grep"; then ok "$name"; else bad "$name (exit $rc, want $want)" "$out"; fi
}
queue() { printf '%s\n' "$@" > "$FAKE_QUEUE"; }

mkdir "$T/repo" && cd "$T/repo" && git init -q && git config user.email t@t && git config user.name t
echo 'def add(a, b): return a - b' > app.py && git add . && git commit -qm base

expect "new scaffolds dir and brief"       0 "created PROJECT.md"   -- "$RL" new t1
expect "init refuses TODO placeholders"    2 "TODO"                 -- "$RL" init t1
sed -i '' 's/TODO[^|]*//g' _review/PROJECT.md _review/cycles/t1/BRIEF.md
sed -i '' 's/^\*\*Type:\*\*.*/**Type:** code/' _review/cycles/t1/BRIEF.md
echo "junk" > stray.txt
expect "init refuses dirty tree"           3 "uncommitted"          -- "$RL" init t1
rm stray.txt
expect "init opens cycle"                  0 "OPENED t1"            -- "$RL" init t1 --trailer "X-Test: 1"
expect "respond refused on reviewer turn"  2 "reviewer's turn"      -- "$RL" respond --decision continue

queue credits
expect "reviewer 402 -> exit 4, graceful"  4 "REVIEW FAILED: out of credits" -- "$RL" review
expect "failed round keeps reviewer turn"  0 "turn=reviewer"        -- "$RL" status

queue vandal
expect "reviewer edits rejected (exit 3)"  3 "vandal.txt"           -- "$RL" review
rm -f vandal.txt _review/cycles/t1/iter-01/review.md

queue good1
expect "round 1 reviewed"                  0 "F-01-01 · major"      -- "$RL" review
expect "review commit made"                0 "iter 01 review"       -- git log --oneline -1
expect "respond needs response.md"         2 "does not exist"       -- "$RL" respond --decision continue
printf '# Response\n\n## Summary\nx\n\n### F-01-01 · ACCEPT\n- fixed\n' > _review/cycles/t1/iter-01/response.md
expect "respond needs every verdict"       2 "F-01-02"              -- "$RL" respond --decision continue
printf '\n### F-01-02 · ACCEPT\n- docstring\n' >> _review/cycles/t1/iter-01/response.md
echo 'def add(a, b):
    "Add."
    return a + b' > app.py
expect "early converge refused"            2 "last recommendation"  -- bash -c "printf 'Outcome: converged\n' > _review/cycles/t1/CLOSE.md; '$RL' respond --decision close"
rm _review/cycles/t1/CLOSE.md
expect "hand over round 1"                 0 "HANDED OVER"          -- "$RL" respond --decision continue
expect "fix committed with trailer"        0 "X-Test: 1"            -- git log -1 --format=%B
expect "changes shows builder diff"        0 "app.py"               -- "$RL" changes

queue bad2 good2
expect "format retry then success"         0 "REVIEWED t1 iteration 02" -- "$RL" review
expect "retry recorded (attempts 2)"       0 '"attempts": 2'        -- cat _review/cycles/t1/STATE.json
expect "prompt listed fixes to verify"     0 "F-01-02"              -- grep -A3 "Verify these" _review/cycles/t1/iter-02/reviewer-prompt.md
expect "ledger shows verified"             0 "verified"             -- "$RL" ledger
printf '# Response\n\n## Summary\nconverged\n' > _review/cycles/t1/iter-02/response.md
printf '# Close — t1\n\nOutcome: converged\nIterations: 2\n' > _review/cycles/t1/CLOSE.md
expect "close converged"                   0 "CLOSED t1: converged" -- "$RL" respond --decision close
expect "tree clean after close"            0 "^$"                   -- bash -c "git status --porcelain; echo"
expect "closed cycle refuses review"       2 "closed"               -- "$RL" review

# cap and budget, on a second cycle
"$RL" new t2 >/dev/null; sed -i '' 's/TODO[^|]*//g' _review/cycles/t2/BRIEF.md
sed -i '' 's/^\*\*Type:\*\*.*/**Type:** plan/' _review/cycles/t2/BRIEF.md
git add -A && git commit -qm brief2
expect "init with max 1, tiny budget"      0 "max=1"                -- "$RL" init t2 --max 1 --budget 0.025
queue good1
expect "round runs within budget"          0 "REVIEWED t2"          -- "$RL" review
printf '# R\n\n### F-01-01 · BACKLOG\nx\n### F-01-02 · REJECT\nx\n' > _review/cycles/t2/iter-01/response.md
expect "cap refuses continue (exit 8)"     8 "cap"                  -- "$RL" respond --decision continue
expect "budget exhausted -> exit 8"        8 "budget"               -- bash -c "'$RL' adjust --max 3 >/dev/null; '$RL' respond --decision continue >/dev/null; '$RL' review"
printf 'Outcome: budget-reached\n' > _review/cycles/t2/CLOSE.md
expect "early close on reviewer turn"      0 "CLOSED t2: budget-reached" -- "$RL" respond --decision close
expect "list shows both"                   0 "budget-reached"       -- "$RL" list

echo
echo "selftest: $pass passed, $fail failed"
[ "$fail" = 0 ]
