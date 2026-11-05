Read AGENTS.md. Before any package of the plan folder $folder runs, check every package row of it against the
code once, so the run does not stop package by package. Do not change any file except $out.
For each row, in order:
1) every file it names exists (or is created by an earlier row of the plan);
2) for each module or function it deletes: search the whole repository (absolute imports, relative imports
   `from . import x`, string paths, Makefile and scripts) for kept files that still use it and are not in the row
   or an earlier row; tests that import deleted code must be deleted or edited by the row;
3) line numbers and function names it gives still match the code (say where they moved);
4) the row does not contradict spec/decisions.md, spec/rules.md or an earlier row (grep the N numbers it names).
Then once for the plan: every scenario (S..) and decision (N..) that $folder/00-overview.md names is covered by
the acceptance of at least one row, and every S.. or N.. a row names exists in spec/. A gap is a problem line
"- 00-overview: S07 has no row - the row whose title covers it and the test to add".
Read the plan rows and the code with grep and small ranges; do not read whole large files.
Write $out exactly like this:
line 1: PREFLIGHT: CLEAN   or   PREFLIGHT: PROBLEMS
then, for PROBLEMS, one line per problem: "- Pn: problem (path:line) - row change that fixes it".
Do not commit. Never run ./dev (it starts a new run).
