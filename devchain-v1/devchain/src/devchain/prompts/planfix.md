Package $package of $plan stopped on a plan problem; the note is $note. Decide whether the answer is already
written down. Do not edit any file except those named below.
Verdict file: $verdict
Read the note, the package row, the sections of the 00-overview.md next to $plan (when there is one) that the row names, the spec/
lines the row and the note name (spec/decisions.md, spec/rules.md, spec/glossary.md: grep -n first, read only
those lines), then grep spec/ (decisions, rules, glossary, concepts, scenarios) for the terms of the problem and
read the hits, and the code the note cites (grep, small ranges). Search the code yourself to confirm each claim.
When the `graphify` command exists, find code with `graphify query "<question>"` or `graphify explain <name>`
before grepping; never open the files in graphify-out/ directly.
Answer from what is written, never from a guess. spec/ wins over the plan; the plan wins over the code. Never
add logic: every behaviour in your fix or answer (a rule, condition, default, threshold, error case, event or
field) must already be stated in spec/ or the plan, and you cite that line. When the fix needs behaviour that is
written nowhere, or spec/ contradicts itself, that is ASK, however obvious the answer looks.
When the note says the package is stuck (the checks still fail after the fix rounds), read every round's
findings and the failing tests and code yourself; the answer is usually one of: a kept test asserts behaviour the
row deletes or changes (name the test and give the exact new assert, or the case to delete when the behaviour is
gone), a caller or file the row misses (FIXED), or a fix in code the row touches (ANSWER with path:line). Say for
each failure what Codex must do. ASK only when the expected behaviour itself is not written down. Judge each
failing test by spec/ alone: when its assert is what spec/ states, the code is wrong; when it contradicts spec/,
the test is old and you give the new assert with the spec/ line.
A kept test that breaks only because of the row's change is not a plan problem: Codex may edit such tests
(task prompt). Answer that with ANSWER (name the test and the edit), not with a row change.
Pick one:
FIXED when the row itself is wrong or incomplete and the fix follows from spec/, the plan or the code: a missing
file or caller, a moved line, a row that must list one more edit, a deletion the spec does not ask for. Then
edit only files in $folder: the row of $package, and a later row only where it names a file this row now removes.
A row you change names the kept tests its change breaks: grep project-a/app/tests/ and
project-a/demo_api/tests/.
ANSWER when the row is right and Codex only needs the answer: what the row means, which spec line decides it,
where the code is. Change no file.
ASK when the answer needs a product decision or new logic, two spec/ files disagree, or you would have to guess. Then append to
$note a section "## Questions for the owner": numbered questions, each with its options and the one you
recommend, and change nothing else.
Never edit spec/, code, or docs outside $folder. Never change what a decision says, widen a package beyond its
title, or drop behaviour the spec keeps.
Write the verdict file exactly like this:
line 1: PLANFIX: FIXED   or   PLANFIX: ANSWER   or   PLANFIX: ASK
then at most 12 lines for Codex, who continues the package with them: each change or each answer, with the
spec/, plan or code line (path:line) that decides it; for ASK, why you ask, and as
the last line `ABOUT: <the Touches topics or paths the question is about, comma-separated>`: rows that share
them wait for the answer.
Do not commit. Never run ./dev (it starts a new run).
