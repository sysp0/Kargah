# QA rule: every bug found is fixed on the branch under test

> History: the design as decided when it was built. The current guide is `docs/devchain/README.md`; plans now live in `docs/devchain-plan/`.

Status: approved by the owner 2026-10-17; implemented by the thread 2026-10-18. Code rows QB1-QB3 below run through `./dev feature qa-own-branch <Pn>`.
Guide text: `docs/devchain.md` (QA section). Replaces the `[APP]`/`[HEAVY]` split of `docs/plan/qa-loop.md`.

## Rules

1. **QA runs on the branch under test.** `./dev qa <suite>` defaults to `--branch current` (the checked-out feature branch) and commits the specs and the fixes there. `--branch auto` (fresh `qa/<suite>` from `main`) stays as an option, for a suite that tests `main` itself. It still refuses to run on the base branch.
2. **Every bug is fixed on that branch, in the same run, whatever its size.** One fix row has at most 5 files; a bigger fix is split into rows. The light-bug limits (`light_max_files`, `heavy_paths`) stop applying.
3. **Triage gives two tags for app bugs**:
   - `[FIX]`: fix it here. Triage writes the row for Codex (see rule 4).
   - `[DECIDE]`: the run stops with `needs_decision`; the owner and the thread decide together. Used when (a) the right fix changes a decision (a D number) or the scenario contradicts the plan, or (b) the bug is old (already in `main`, not in this branch's diff) and the fix is large (more than 3 files, or under `app/engine/` or `app/migrations/`), because it would bury the package PR. A small old bug is `[FIX]`.
   - `[TEST]` (the spec is wrong) and `[ENV]` (the stack is wrong) stay as they are.
4. **Sonnet describes how to fix** (the triage session). Every `[FIX]` row in `docs/plan/qa-fix-<run-id>.md` has: Cause (`path:line`, what the code does wrong, one or two sentences), Change (the exact edit per file), Test (the failing spec or a pytest, written first), Do not touch (files outside the row). Codex implements only that row.
5. **Origin check.** Triage runs `git diff origin/main...HEAD --stat` and says whether the cause is in this branch's hunks (quote `path:line`) or old. The tool checks the size of an old-bug row itself: more than 3 files or a heavy path turns it into `[DECIDE]`.
6. `docs/qa/heavy/` notes and `docs/plan/bugfix-<name>.md` stay, for `[DECIDE]` items only.

## Packages (`./dev feature qa-own-branch <Pn>`)

| Pn | Title | files | acceptance |
|---|---|---|---|
| QB1 | Triage prompt: `[FIX]` / `[DECIDE]` and the row layout | `devchain/src/devchain/prompts/triage.md`, `devchain/tests/test_qa.py` | `test_triage_prompt_tags` checks the prompt names `[FIX]`, `[DECIDE]`, `git diff origin/main...HEAD` and Cause/Change/Test/Do-not-touch |
| QB2 | Verdict parsing and row check | `devchain/src/devchain/qa.py`, `devchain/tests/test_qa.py` | with fakes: a `[FIX]` row of 5 files runs on the same branch; a 6-file row is held with "split into rows"; an old-bug row with 4 files becomes `[DECIDE]` and the run ends `needs_decision`; `[DECIDE]` writes `docs/qa/heavy/<run>-<S>.md` |
| QB3 | Default branch mode and settings | `devchain/src/devchain/cli.py`, `devchain.toml`, `devchain/tests/test_core.py`, `docs/devchain.md` | `./dev qa x` defaults to `current`; `qa.fix_max_files = 5` and `qa.old_bug_max_files = 3` are read from the config; the guide matches |

## Open questions

1. An old small bug fixed in the package branch: own commit so the reviewer sees it? Recommended: yes; the fix row title starts with `old:`.
