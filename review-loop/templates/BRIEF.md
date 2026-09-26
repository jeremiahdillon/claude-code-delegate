# Brief — cycle `{cycle}`

<!-- The builder fills this in; the reviewer reads it every round. Replace every
     TODO. Keep the headings: `review-loop init` checks for them. A strong brief
     is the biggest single factor in review quality. -->

**Type:** TODO code | plan | other

## 1. What you are reviewing

TODO: what was built or proposed and why, in a short paragraph. Name the exact
target, for example:
- **Code:** `git diff <base>..HEAD -- <paths>`, where `<base>` is the commit just
  before the work. Name the design or plan it implements, if there is one.
- **Plan or spec:** the document path(s), and the codebase it must fit.

## 2. In scope

TODO: the files, directories or documents the reviewer should read. Add
reference-only material (read, don't review) separately.

## 3. Out of scope: do not read

TODO: paths the reviewer must never open (secrets, personal data, unrelated
areas), and areas not to review. Write "None" if there are none.

## 4. Intent to hold the work against

TODO: the goals, principles and invariants the work must satisfy. These are
the yardstick for "blocker" and "major".

## 5. Settled decisions: do not re-argue

TODO: decisions the user has made. The reviewer may flag a concrete risk in one
once, as `settled-risk`. Write "None" if there are none.

## 6. Forward references: not defects

TODO: things intentionally not built yet. Write "None" if there are none.

## 7. Known limitations: already acknowledged

TODO, or "None".

## 8. Checks you may run

TODO: read-only commands (tests, linters, validators), e.g. `npm test`,
`pytest -q`. Also what must never be run (anything that deploys, sends,
spends, or writes outside a temp copy). Write "None" for pure document reviews.

## 9. Review checklist, in priority order

TODO: 4–10 specific questions, most important first. Name the functions, steps
or sections where the risk lies. Generic checklists get generic reviews.
