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
sed -i '' 's/^\*\*Lenses:\*\*.*/**Lenses:** code/' _review/cycles/t1/BRIEF.md
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
sed -i '' 's/^\*\*Lenses:\*\*.*/**Type:** plan/' _review/cycles/t2/BRIEF.md   # legacy form
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


# ---------------------------------------------------------------- lenses and categories
expect "t1 prompt has the code lens"       0 "### Lens: code"       -- cat _review/cycles/t1/iter-01/reviewer-prompt.md
expect "t1 close has round summary"        0 "## Round summary"     -- cat _review/cycles/t1/CLOSE.md
expect "summary counts failed attempts"    0 "failed attempt"       -- cat _review/cycles/t1/CLOSE.md
expect "summary row for round 1"           0 "| 1 | 0 | 1 | 1 | 0 |" -- cat _review/cycles/t1/CLOSE.md
expect "status prints round summary"       0 "Fixes verified"       -- "$RL" status --cycle t1
expect "summary verdict order"              0 "| 0 / 0 / 1 / 1 |"   -- bash -c "'$RL' status --cycle t2 | grep '^| 1 '"
expect "legacy Type keeps security"        0 '"security"'           -- cat _review/cycles/t2/STATE.json

fill() { # fill TODOs in a brief (and PROJECT.md) and set its lens line
  sed -i '' 's/TODO[^|]*//g' "$1"; [ -f "$(dirname "$1")/../../PROJECT.md" ] && sed -i '' 's/TODO[^|]*//g' "$(dirname "$1")/../../PROJECT.md"
  sed -i '' "s/^\*\*Lenses:\*\*.*/**Lenses:** $2/" "$1"
}
"$RL" new t3 >/dev/null; fill _review/cycles/t3/BRIEF.md "writing, analysis"; git add -A && git commit -qm brief3
expect "unknown lens refused"              2 "unknown lens"         -- bash -c "sed -i '' 's/^\*\*Lenses:\*\*.*/**Lenses:** writing, nosuch/' _review/cycles/t3/BRIEF.md; '$RL' init t3"
git checkout -q -- _review/cycles/t3/BRIEF.md
expect "init with two lenses"              0 "lenses=writing, analysis" -- "$RL" init t3
queue badcat badcat badcat
expect "category outside lenses rejected"  9 "not one of"           -- "$RL" review
rm -f _review/cycles/t3/iter-01/review.md
queue multi1
expect "a category from each lens is ok"   0 "argument"             -- "$RL" review
P3=_review/cycles/t3/iter-01/reviewer-prompt.md
expect "prompt: writing lens first"        0 "writing"              -- bash -c "grep -o '### Lens: [a-z]*' $P3 | head -1"
expect "prompt: analysis lens second"      0 "analysis"             -- bash -c "grep -o '### Lens: [a-z]*' $P3 | sed -n 2p"
printf 'Outcome: aborted\n' > _review/cycles/t3/CLOSE.md
printf '# R\n\n### F-01-01 · BACKLOG\nx\n### F-01-02 · BACKLOG\nx\n' > _review/cycles/t3/iter-01/response.md
"$RL" respond --decision close >/dev/null

# a cycle opened before lenses existed: no lenses/categories/targets in STATE.json
"$RL" new t4 >/dev/null; sed -i '' 's/TODO[^|]*//g' _review/cycles/t4/BRIEF.md
sed -i '' 's/^\*\*Lenses:\*\*.*/**Type:** other/' _review/cycles/t4/BRIEF.md; git add -A && git commit -qm brief4
"$RL" init t4 >/dev/null
python3 - <<'EOF'
import json; p = "_review/cycles/t4/STATE.json"; s = json.load(open(p))
for k in ("lenses", "categories", "targets", "refs", "setup"): s.pop(k, None)
json.dump(s, open(p, "w"), indent=2)
EOF
git add -A && git commit -qm oldstate
queue good1
expect "old-format state still reviews"    0 "REVIEWED t4"          -- "$RL" review
expect "old state -> general lens"         0 "### Lens: general"    -- cat _review/cycles/t4/iter-01/reviewer-prompt.md
expect "old state -> legacy categories"    0 "over-engineering"     -- cat _review/cycles/t4/iter-01/reviewer-prompt.md
printf 'Outcome: aborted\n' > _review/cycles/t4/CLOSE.md
printf '# R\n\n### F-01-01 · BACKLOG\nx\n### F-01-02 · BACKLOG\nx\n' > _review/cycles/t4/iter-01/response.md
"$RL" respond --decision close >/dev/null

# ---------------------------------------------------------------- setup decision (new --target)
python3 "$HERE/../../delegate/tests/make_fixtures.py" "$T/fx" >/dev/null
export WS="$T/workspaces"
cd "$T"
mkdir other && (cd other && git init -q && git config user.email t@t && git config user.name t && echo x > x && git add . && git commit -qm x)
expect "--target needs --lenses"           2 "--lenses is required" -- "$RL" new s1 --target "$T/repo/app.py"
expect "row 3: root follows the target"    0 "ROOT: .*/repo$"       -- "$RL" --repo "$T/other" new s1 --target "$T/repo/app.py" --lenses code
expect "row 3: in-place recorded"          0 '"row": 3'             -- cat "$T/repo/_review/cycles/s1/SETUP.json"
expect "row 3: target path in tree"        0 '"app.py"'             -- cat "$T/repo/_review/cycles/s1/SETUP.json"
echo dirt > "$T/repo/dirt.txt"
expect "row 4: dirty asks"                 2 "NEEDS DECISION"       -- "$RL" new s2 --target "$T/repo/app.py" --lenses code
rm "$T/repo/dirt.txt"
expect "row 2: two repos asks"             2 "NEEDS DECISION"       -- "$RL" new s2 --target "$T/repo/app.py" --target "$T/other/x" --lenses code
(cd "$T/repo" && mkdir -p build && echo gen > build/out.txt && echo "build/" >> .git/info/exclude)
expect "row 1: ignored -> workspace"       0 "decision row 1"       -- "$RL" new s3 --target "$T/repo/build" --lenses writing --workspace-root "$WS"
mkdir proj && echo '{}' > proj/package.json && echo 'SECRET=1' > proj/.env && echo 'code' > proj/main.js
expect "row 5: project asks"               2 "NEEDS DECISION"       -- "$RL" new s4 --target "$T/proj" --lenses code
expect "row 5: init when chosen"           0 "EXCLUDED from git (deny list): .env" -- "$RL" new s4 --target "$T/proj" --lenses code --setup init
expect "init: snapshot committed"          0 "initial snapshot"     -- git -C "$T/proj" log --oneline -1
expect "init: .env not committed"          0 "^$"                   -- bash -c "git -C '$T/proj' ls-files .env; echo"
sed -i '' 's/TODO[^|]*//g' proj/_review/PROJECT.md proj/_review/cycles/s4/BRIEF.md
sed -i '' 's/^\*\*Lenses:\*\*.*/**Lenses:** writing/' proj/_review/cycles/s4/BRIEF.md
git -C proj add -A && git -C proj commit -qm brief
expect "lens flip after new is refused"    2 "no longer match"      -- "$RL" --repo "$T/proj" init s4

# ---------------------------------------------------------------- in-place references
mkdir src && cp fx/sample.pdf src/ && echo "notes" > src/notes.md
expect "in-place ref copied"               0 ".delegate/ref/s5/src" -- "$RL" new s5 --target "$T/repo/app.py" --ref "$T/src" --lenses code
expect "ref dir excluded from git"         0 ".delegate/"           -- cat "$T/repo/.git/info/exclude"
expect "ref not visible to git"            0 "^$"                   -- bash -c "cd '$T/repo' && git status --porcelain --untracked-files=all | grep delegate; echo"

# ---------------------------------------------------------------- workspace, extraction, apply
mkdir -p docs && printf '# Essay\n\nFirst draft.\n' > docs/essay.md && echo keep > docs/notes.md \
  && echo old > docs/old.md && echo gone > docs/gone.md && cp fx/sample.docx docs/table.docx
expect "row 6: workspace, no question"     0 "decision row 6"       -- "$RL" new w1 --target "$T/docs" --ref "$T/fx/sample.xlsx" --lenses "writing, quantitative" --workspace-root "$WS"
W=$(ls -d "$WS"/w1-*)
expect "workspace SOURCES.json"            0 '"in_tree": "work/docs"' -- cat "$W/SOURCES.json"
expect "workspace refuses reuse"           2 "never reused"         -- "$RL" new w1 --target "$T/docs" --ref "$T/fx/sample.xlsx" --lenses "writing, quantitative" --workspace-root "$WS"
sed -i '' 's/TODO[^|]*//g' "$W/_review/PROJECT.md" "$W/_review/cycles/w1/BRIEF.md"
git -C "$W" add -A && git -C "$W" commit -qm brief
expect "init extracts binaries"            0 "text renditions: 2"   -- "$RL" --repo "$W" init w1
expect "docx rendition"                    0 "Quarterly Review"     -- cat "$W/_review/extract/work/docs/table.docx.md"
expect "xlsx ref rendition"                0 "SUM(B1:B1)"           -- cat "$W/_review/extract/ref/sample.xlsx.md"
queue good1
expect "workspace round 1"                 0 "REVIEWED w1"          -- "$RL" --repo "$W" review
expect "prompt lists renditions"           0 "table.docx.md"        -- cat "$W/_review/cycles/w1/iter-01/reviewer-prompt.md"
expect "prompt lists targets"              0 "Under review.*work/docs" -- cat "$W/_review/cycles/w1/iter-01/reviewer-prompt.md"
printf '# Essay\n\nSecond draft.\n' > "$W/work/docs/essay.md"
cp fx/sample.pptx "$W/work/docs/slides.pptx"; rm "$W/work/docs/gone.md"
printf '# R\n\n### F-01-01 · ACCEPT\nx\n### F-01-02 · ACCEPT\nx\n' > "$W/_review/cycles/w1/iter-01/response.md"
expect "respond hands over"                0 "HANDED OVER"          -- "$RL" --repo "$W" respond --decision continue
expect "respond re-extracted new file"     0 "Market Overview"      -- cat "$W/_review/extract/work/docs/slides.pptx.md"
queue good2
"$RL" --repo "$W" review >/dev/null
expect "round-2 diff shows the rendition"  0 "slides.pptx.md"       -- cat "$W/_review/cycles/w1/iter-02/reviewer-prompt.md"
printf '# R\n\n## Summary\nok\n' > "$W/_review/cycles/w1/iter-02/response.md"; printf 'Outcome: converged\n' > "$W/_review/cycles/w1/CLOSE.md"
expect "close offers apply"                0 "review-loop apply"    -- "$RL" --repo "$W" respond --decision close
expect "apply dry run"                     0 "WOULD modify .*essay.md" -- "$RL" --repo "$W" apply
expect "dry run changed nothing"           0 "First draft"          -- cat docs/essay.md
expect "new file needs --include-new"      0 "pass --include-new"   -- "$RL" --repo "$W" apply
expect "delete needs --include-deletes"    0 "pass --include-deletes" -- "$RL" --repo "$W" apply
# conflicts: original changed under a modified file / new file's destination exists / deleted file's original changed
echo "edited elsewhere" > docs/notes.md; echo "ws edit" > "$W/work/docs/notes.md"
echo "someone else's" > docs/new2.md; echo mine > "$W/work/docs/new2.md"
echo "changed" > docs/old.md; rm "$W/work/docs/old.md"
expect "apply stops on conflicts"          3 "3 conflict"           -- "$RL" --repo "$W" apply --yes --include-new --include-deletes
expect "modified applied"                  0 "Second draft"         -- cat docs/essay.md
expect "new applied"                       0 "Market Overview"      -- "$HERE/../../delegate/bin/delegate-extract" docs/slides.pptx
expect "clean delete applied"              0 "gone"                 -- bash -c "[ ! -e docs/gone.md ] && echo gone"
expect "modified-conflict untouched"       0 "edited elsewhere"     -- cat docs/notes.md
expect "new-conflict untouched"            0 "someone else's"       -- cat docs/new2.md
expect "delete-conflict untouched"         0 "changed"              -- cat docs/old.md
expect "apply outside workspace refused"   2 "workspace cycles only" -- "$RL" --repo "$T/repo" apply

# ---------------------------------------------------------------- git-ignored review dir
mkdir ign && cd ign && git init -q && git config user.email t@t && git config user.name t
printf '.delegate/\n' > .gitignore && echo a > a.txt && git add . && git commit -qm base
"$RL" --review-dir .delegate/review new g1 >/dev/null
sed -i '' 's/TODO[^|]*//g' .delegate/review/PROJECT.md .delegate/review/cycles/g1/BRIEF.md
sed -i '' 's/^\*\*Lenses:\*\*.*/**Lenses:** general/' .delegate/review/cycles/g1/BRIEF.md
expect "ignored review dir: init works"    0 "OPENED g1"            -- "$RL" --review-dir .delegate/review init g1
queue good1
expect "ignored review dir: review works"  0 "REVIEWED g1"          -- "$RL" --review-dir .delegate/review review
printf '# R\n\n### F-01-01 · ACCEPT\nx\n### F-01-02 · ACCEPT\nx\n' > .delegate/review/cycles/g1/iter-01/response.md
echo b > a.txt
expect "ignored review dir: respond works" 0 "HANDED OVER"          -- "$RL" --review-dir .delegate/review respond --decision continue
expect "records stay out of git"           0 "^$"                   -- bash -c "git ls-files .delegate; echo"
expect "builder change committed"          0 "a.txt"                -- git show --stat --format= HEAD

echo
echo "selftest: $pass passed, $fail failed"
[ "$fail" = 0 ]
