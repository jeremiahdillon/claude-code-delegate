#!/usr/bin/env python3
"""Fake reviewer for selftest.sh. Called as: fake_reviewer.py PROMPT_FILE OUT_FILE.

Behaviour comes from $FAKE (one scenario per call, consumed from a queue file):
  good1        iteration-1 review: one major, one minor; recommend continue
  good2        iteration-2 review: verifies F-01-01 and F-01-02; recommend converge
  bad2         iteration-2 review missing the V- item for F-01-02 (format failure)
  credits      exit 4 like delegate-agent on HTTP 402
  vandal       writes a file outside the review dir, then a valid review
  multi1       iteration-1 review using one category from the writing lens and one from analysis
  badcat       iteration-1 review using a category no lens of a writing/analysis cycle allows
Queue: $FAKE_QUEUE is a file of scenario names, one per line; each call pops the first.
"""
import os
import sys
from pathlib import Path

prompt, out = Path(sys.argv[1]), Path(sys.argv[2])
q = Path(os.environ["FAKE_QUEUE"])
lines = q.read_text().split()
scenario, rest = lines[0], lines[1:]
q.write_text("\n".join(rest) + "\n")
cycle = "t1"

R1 = f"""# Review — {cycle} — iteration 01

## Summary
Two problems.

## New findings
### F-01-01 · major · correctness
- **Location:** `app.py:1`
- **Finding:** add() subtracts.
- **Evidence:** ran it
- **Suggested fix:** use +

### F-01-02 · minor · clarity
- **Location:** `app.py:1`
- **Finding:** no docstring.
- **Evidence:** read it
- **Suggested fix:** add one

## Recommendation: continue
"""

R2 = f"""# Review — {cycle} — iteration 02

## Summary
Fixed.

## Verification of previous fixes
### V-02-01 · F-01-01 · verified
now adds.
{{v2}}
## New findings
None.

## Recommendation: converge
"""

if scenario == "credits":
    print("error: OpenCode reported: 402 Payment Required (cost $0.0100)", file=sys.stderr)
    sys.exit(4)
if scenario == "vandal":
    (Path.cwd() / "vandal.txt").write_text("oops\n")
    out.write_text(R1)
elif scenario == "good1":
    out.write_text(R1)
elif scenario == "good2":
    out.write_text(R2.replace("{v2}", "### V-02-02 · F-01-02 · verified\ndocstring added.\n"))
elif scenario == "multi1":
    out.write_text(R1.replace("· major · correctness", "· major · argument")
                     .replace("· minor · clarity", "· minor · reasoning"))
elif scenario == "badcat":
    out.write_text(R1.replace("· major · correctness", "· major · performance"))
elif scenario == "bad2":
    out.write_text(R2.replace("{v2}", ""))
print(f"DONE: {out}  model=fake mode=plan session=ses_fake{len(rest)} steps=1 tools=0 cost=$0.0100 time=0.1s")
