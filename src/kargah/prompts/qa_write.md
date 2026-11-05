Read AGENTS.md, then scenario $scenario in $suite (grep -n "^## $scenario" first and read only that section,
plus the "Data" and "Conventions" sections of the same file).
Write the Playwright spec $spec for that scenario only, with @playwright/test and TypeScript.
- One test per numbered step group of the scenario; each expected result in the scenario is one assertion.
- Locate elements by role and accessible name or label (getByRole, getByLabel, getByText with the exact Persian
  text from project-ui/ui/src/screens.jsx). No CSS classes, no nth() indexes, no fixed sleeps.
- Import test, expect and the helpers from qa/fixtures.ts (api fixture, seed(), latin(), path(), ingest()).
  Prepare with the api fixture only what the scenario does not test; do the tested steps in the UI.
- Expected values come only from the scenario text. Never weaken an expectation to make it pass.
- Change only files under qa/. Never change app code, even if you think the app is wrong.
You cannot run the browser or reach the services from your sandbox. The tool runs the spec outside the sandbox
and sends you the exact failure. Do not write Blocked: for that.
Do not commit. Do not push. End with at most 10 lines: files changed, what each test checks.
Never run ./dev (it starts a new run). Do not run Playwright here: after you finish, the tool resets the QA data,
runs $spec in the browser and sends you the result.
