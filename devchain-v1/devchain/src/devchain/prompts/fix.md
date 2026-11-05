Read AGENTS.md. You are fixing package $package of $plan. Your earlier change is in the working tree (git diff).
Fix ONLY these findings, nothing else:
$findings
$rules
Kept tests your change breaks are part of the package, not a plan problem: when a test file the row does not
list fails only because of this row's change (it imports, patches or asserts code or behaviour the row deletes or
changes), edit that test file too: drop the import, delete the case of the deleted code, or change the assert to
the behaviour the row asks for. Never weaken a test of behaviour the row keeps, and never edit non-test files the
row does not list. Name each such test file in your summary. A kept test that already fails because an earlier
package of this plan removed or changed what it uses is fixed the same way.
When the row changes behaviour (not only names), grep the tests for the functions, routes, events and values
involved and update every assert of the old behaviour now; the sandbox cannot run them, so do not wait for
the acceptance check to find them.
A failing kept test is fixed this way; it is not a reason to stop.
When a finding asks you to remove or revert an edit that a check needs (the acceptance test or a kept test fails
without it), keep the edit and name in your summary the test that needs it, with path:line; the review reads your
summary.
STOP instead of guessing when the plan or the spec is the problem: the row is unclear, two documents disagree,
or the code is not what the plan describes. Then write $note in English: 1) what the row asks; 2) what is unclear
or wrong, with path:line in the plan, spec/ or the code; 3) what you checked or tried; 4) the options and the one
you recommend. Set the line `Blocked: plan problem, see $note` in docs/progress.md and stop. The plan check
reads the note against spec/ and you continue with its answer; only what spec/ does not decide reaches the owner.
Do not commit. Do not push. End with at most 10 lines: what you changed, test summary line.
Never run ./dev (it starts a new run); run single tests directly.
