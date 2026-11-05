You review the Playwright spec $spec for scenario $scenario of $suite. The tool ran it and it passed.
Do not edit any file except the verdict file.
Verdict file: $verdict
Read the scenario section in $suite (grep -n "^## $scenario" first) and the spec (git diff and the file).
Check: 1) every expected result of the scenario has an assertion that would fail if the app were wrong;
2) no test.skip/fail/fixme, no assertion that is always true, no catch that hides a failure, no fixed sleep;
3) locators use roles, labels or exact text, not CSS classes or indexes; 4) only files under qa/ changed.
Write the verdict file exactly like this:
line 1: VERDICT: PASS   or   VERDICT: FIX
if FIX, then a numbered list of at most 10 items, each "path:line - problem - expected". Nothing else.
Never run ./dev (it starts a new run). To rerun this one spec yourself (at most once, e.g. to check timing):
make -C project-a qa-reset && cd qa && npx playwright test $spec --reporter=line
