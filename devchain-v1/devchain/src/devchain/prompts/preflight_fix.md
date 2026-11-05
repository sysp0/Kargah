The preflight check of the plan folder $folder found problems in its package rows; they are listed in $out.
Fix the plan once, before any package runs. Do not edit any file except those named below.
Verdict file: $verdict
For each problem: confirm it with grep and small ranges in the code, then read the spec/ lines that decide it
(spec/decisions.md, spec/rules.md, spec/glossary.md: grep -n first, read only those lines).
Fix a row only when the fix follows from spec/, the plan or the code without a guess: add the missing file or
caller, move a line number, add the test that goes with code the row deletes, drop a deletion the spec does not
ask for. Edit only files in $folder. Never edit spec/ or code, never change what a decision says, never widen a
package beyond its title or drop behaviour the spec keeps. A problem that is not real: leave the row.
A scenario or decision with no row: add its test to the acceptance of the row whose title covers it; when no
row's title covers it, ask.
When an answer needs a product decision, two documents disagree, or you would have to guess, append to $out a
section "## Questions for the owner": numbered questions, each with its options and the one you recommend.
Write the verdict file exactly like this:
line 1: PLANFIX: FIXED   (every problem fixed or not real)   or   PLANFIX: ASK   (at least one question)
then at most 15 lines: each change (row, what changed, the spec/plan/code line that decides it).
Do not commit. Never run ./dev (it starts a new run).
