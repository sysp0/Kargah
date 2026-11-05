Read AGENTS.md and docs/progress.md.
Do ONLY package $package of $plan: its row in the packages table, plus the sections of $plan, of the
00-overview.md next to it when there is one (its "Read first" line), of docs/design/time-and-source-routing.md and the spec/ lines
that the row names. Do not read other packages, the rest of spec/, lockfiles, graphify-out/, .claude/, .codex/ or
.devchain/.
$rules
Start with a failing test, then make the change. Touch only the files the row lists (about 5).
Kept tests your change breaks are part of the package, not a plan problem: when a test file the row does not
list fails only because of this row's change (it imports, patches or asserts code or behaviour the row deletes or
changes), edit that test file too: drop the import, delete the case of the deleted code, or change the assert to
the behaviour the row asks for. Never weaken a test of behaviour the row keeps, and never edit non-test files the
row does not list. Name each such test file in your summary. A kept test that already fails because an earlier
package of this plan removed or changed what it uses is fixed the same way.
When the row changes behaviour (not only names), grep the tests for the functions, routes, events and values
involved and update every assert of the old behaviour now; the sandbox cannot run them, so do not wait for
the acceptance check to find them.
Before finishing, grep the repository (tests, scripts, Makefile; relative imports too) for every module, function
and name you deleted or renamed, and fix the kept tests that still use them.
Run only the related test file: check `pgrep -af pytest` first (never two runs at once), then
`scripts/check.sh project-a/app/tests/<file>`. The sandbox cannot reach the databases: never mark a package blocked for that;
the tool runs the real acceptance check outside the sandbox and sends you the failures.
Update the Pkgs: line in docs/progress.md.
Open questions and issues of this plan now: $holders. When you find that this row needs the answer to one of
them, or a row that is not built yet (it would change the same code or decide what this row builds), do not
guess and do not build around it: set the line `Blocked: WAITS FOR: #60 - <why, one line>` (or
`WAITS FOR: P12`) in docs/progress.md and stop. The work stays; the task goes on when that is resolved.
STOP instead of guessing when the plan or the spec is the problem: the row is unclear, two documents disagree,
or the code is not what the plan describes. Then write $note in English: 1) what the row asks; 2) what is unclear
or wrong, with path:line in the plan, spec/ or the code; 3) what you checked or tried; 4) the options and the one
you recommend. Set the line `Blocked: plan problem, see $note` in docs/progress.md and stop. The plan check
reads the note against spec/ and you continue with its answer; only what spec/ does not decide reaches the owner.
Do not commit. Do not push. End with at most 10 lines: files changed, test summary line, open points.
Never run ./dev (it starts a new run); run single tests directly.
