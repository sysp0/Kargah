---
description: Build the plan packages with Codex, one by one: check, review once, commit. Stops only at a question.
argument-hint: [Pn] [claude]
---
# /build
$ARGUMENTS — empty: build every package not yet built, in plan order, until the plan is done. A package id: build only
that one. Add `claude` to skip Codex.
Read only `docs/progress.md` and the package row. Plan = the `Plan:` folder name there. Never paste file bodies into a brief.

1. **Start.** `base=$(git rev-parse HEAD)`. The tree must be clean (`git status --short`); if not, ask.
   A `UI:` row without `ui-<Pn>.md` next to its part: call `ui-designer` first.
2. **Build.** Run `scripts/codex-pkg.sh <plan> <Pn>` in the background (`run_in_background`) and wait for it.
   Exit 3 (Codex limit) or `claude` in the arguments: call `implementer` with plan and Pn instead.
3. **Check.** Run the package acceptance (`scripts/check.sh <path>`) yourself. Then prove the new tests guard the change:
   copy the package's changed source files (not the tests) aside, restore them from `$base` (`git show $base:<path>`;
   no stash), run the new tests and require a failure, then copy the new files back. No failure:
   send it back as a must-fix (the test does not guard the change). On failure write the last lines to
   `.claude/codex/<plan>-<Pn>.note` and repeat step 2 with that note file once (Codex resumes its session;
   `implementer` gets the note path). A second failure: stop and show it to the owner.
4. **Review.** Call `reviewer` once with `Base: $base`, the plan path and Pn. Must-fix items: write them to the
   note file, one more build round (step 2 with the note), check again. Should-fix and nits: list them, do not fix.
**Bugs.** A bug the owner names in the chat goes first: add a row `P<n>a` under its package (≤5 files, failing test
named) and build it before the next package. No GitHub issues.

5. **Ambiguity** (a `STATUS: blocked`, an `UNCLEAR:` line, a `Blocked:` in progress, code against `spec/`):
   ask the owner in the chat with options and a recommendation. Do not guess, do not change a decision in `spec/`.
6. **Done.** Add one line under `## Current` in `docs/progress.md`: `P13b done: files, tests, review, should-fix`,
   at most ~200 chars, never append to a shared line; details stay in the plan folder. Commit only the package's files and `docs/progress.md`:
   `feat(<plan>): <Pn> <title>`. Do not push unless the owner asked. Report in ≤6 lines: files, tests, review, next.

Then go on to the next package (step 1) without asking. Stop only at step 3's second failure or step 5, or when
the plan is done; then report what was built and what is left.
