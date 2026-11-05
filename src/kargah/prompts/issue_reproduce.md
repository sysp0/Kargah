Read AGENTS.md, then row $package of $plan (grep -n "$package" $plan; read its table row and its section
"## $package"). The section quotes the reporter's scenario: what they did and what they expected.
Write ONE Playwright spec, $spec, that reproduces it, with @playwright/test and TypeScript. It is written before
the fix and must FAIL on the current code when the problem is real.
- Each expected result of the scenario is one assertion with the scenario's numbers and texts. Assert the
  expected behaviour, never the wrong behaviour the reporter saw.
- The stack runs with the QA data set `$seed` (the project of the same name). shop: the "Data" section of the
  suites in docs/qa/ and project-a/demo_seed/qa.py. gsc: Search Console pages, project-a/demo_seed/gsc.py
  (PAGES and its rules give every number).
- Import test, expect and the helpers from qa/fixtures.ts (api fixture, seed(), latin(), path(), ingest()); the
  specs in qa/tests/ show the conventions.
  Locate elements by role and accessible name or label. No CSS classes, no nth() indexes, no fixed sleeps.
- Change only $spec. Never change app code, fixtures or other specs.
You cannot run the browser from your sandbox: after you finish, the tool resets the QA data and runs the spec on
the current code. Do not write Blocked: for that. Do not commit. Do not push. Never run ./dev.
End with at most 5 lines: the assertion that should fail now and why.
