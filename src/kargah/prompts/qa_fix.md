Read AGENTS.md. You are fixing the Playwright spec $spec for scenario $scenario of $suite. Your earlier change is
in the working tree (git diff). Fix ONLY these findings, nothing else:
$findings
Change only files under qa/. Never change app code. Never remove or weaken an assertion of the scenario's
expected results, never add test.skip, test.fail or test.fixme, and never only raise a timeout.
Do not commit. Do not push. End with at most 10 lines: what you changed.
Never run ./dev (it starts a new run). Do not run Playwright here: after you finish, the tool resets the QA data,
runs $spec in the browser and sends you the result.
