Read AGENTS.md, docs/progress.md and project-ui/ui/AGENTS.md.
Do ONLY package $package of $plan: a UI row. Its row in the packages table, the sections of $plan (and of the
00-overview.md next to it) that it names, the UI spec $ui_spec, and $design. Do not read other packages, the rest
of spec/, lockfiles, graphify-out/, .claude/, .codex/ or .devchain/.
$rules
UI rules:
- $ui_spec is the design: build its Layout, Texts and States exactly. $design is the look: reuse its tokens and
  component classes; no new colour, font size or radius; logical CSS only (inline-start/end, never left/right);
  codes and URLs left to right with `.ltr`. Persian texts exactly as the spec writes them.
- Touch only the files the row lists, plus the row's Playwright spec $shots_spec.
- Write $shots_spec (import { test, expect } from "../../fixtures"): one test per item of the spec's "Capture"
  list. Each test starts at "/", reaches the state with the listed clicks and inputs, asserts with expect the
  Persian texts that state must show, then saves
  `await page.screenshot({ path: test.info().outputPath("<nn>-<state>.png"), fullPage: true })`.
  These screenshots are what the UI review looks at.
- You cannot run the browser or the UI build in the sandbox. The tool builds the UI, runs the smoke specs and
  $shots_spec, and sends you the exact errors.
Update the Pkgs: line in docs/progress.md.
Open questions and issues of this plan now: $holders. When you find that this row needs the answer to one of
them, or a row that is not built yet (it would change the same code or decide what this row builds), do not
guess and do not build around it: set the line `Blocked: WAITS FOR: #60 - <why, one line>` (or
`WAITS FOR: P12`) in docs/progress.md and stop. The work stays; the task goes on when that is resolved.
STOP instead of guessing when the row, the UI spec or $design is the problem: they disagree, a state or text is
missing, or the code is not what they describe. Then write $note in English: 1) what the row asks; 2) the problem
with path:line; 3) what you checked; 4) the options and the one you recommend. Set the line
`Blocked: plan problem, see $note` in docs/progress.md and stop.
Do not commit. Do not push. End with at most 10 lines: files changed, open points.
Never run ./dev (it starts a new run).
