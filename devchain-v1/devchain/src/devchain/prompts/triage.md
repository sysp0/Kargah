You triage a failing Playwright spec of a QA scenario. Do not change app code or the spec.
Scenario: $scenario in $suite (grep -n "^## $scenario" first, read that section and the "Data" section).
Spec: $spec. Playwright output tail: $output. Failure artifacts (page snapshot error-context.md, screenshots):
$artifacts
Read the output, then each error-context.md (it shows the page at the failure). Open a screenshot only when the
snapshot is not enough. To find the cause, read the app code with grep and small line ranges
(project-ui/ui/src/, project-a/demo_api/, project-a/app/engine/). Read the plan sections the
scenario cites. Decide for each failure:
- [TEST]: the spec is wrong (wrong locator, wrong label, timing, wrong expectation compared with the scenario).
- [APP]: the spec matches the scenario and the app does not. devchain files it as an issue; its triage plans the fix.
- [ENV]: the QA stack itself is wrong, not the app (wrong data, a service down, a foreign server on a QA port).
Write the verdict file $verdict exactly like this:
line 1: VERDICT: TEST, VERDICT: APP, VERDICT: BOTH, or VERDICT: ENV
then one line per finding: "[TEST] qa/path:line - problem - expected" or
"[APP] app/path:line - expected (scenario step) - actual (what the page or API showed)" or
"[ENV] what is wrong with the stack - the evidence".
For [APP] also write $issue_file, the issue devchain files, in English, exactly with these headings:
### Plan
$plan
### Part
$part
### Package
<the row the scenario checks, like P14, or unknown>
### Kind
Bug
### Tested commit
$commit
### Steps
<the scenario steps that fail, numbered, with the data>
### Expected
<the expected values from the scenario, with numbers>
### Actual
<what the page or API showed>
### Scenario
$scenario in $suite; spec $spec
### Seed
$seed
### Related tasks
<the rows the bug is in, like P14; with path:line of the cause>
Never run ./dev. To rerun this one spec yourself (at most once, e.g. to check timing):
make -C project-a qa-reset && cd qa && npx playwright test $spec --reporter=line
