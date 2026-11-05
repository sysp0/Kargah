# devchain process log

The owner's development flow with devchain, and every change to it, in order. `docs/devchain/README.md` says how each
command works; `docs/devchain/thread-workflow.md` says how the project thread works. This file says what was decided,
when, and why. Newest entry last. Add a line here with every change to the flow.

## The flow today (2026-10-19)

1. **Plan.** The thread writes a plan folder `docs/devchain-plan/<date>-<name>/`: parts in run order, rows `Pn`,
   no open question. The plan lives on one branch `plan/<plan>`, never on main.
2. **Build.** `./dev feature <plan> --detach`: Codex writes each package, devchain checks it (acceptance, tests, UI build,
   UI smoke), a fresh Claude reviews it, devchain commits. A finished part stops at its gate.
3. **Test a part while the plan goes on.** The owner runs `./dev try <part> [--seed shop|gsc]` (own folder, ports and
   databases, fresh seed data each time). A bug is filed as an issue with a scenario; devchain reproduces it with a
   failing spec before it fixes it (reproduce-first). `./dev approve <part|all>` or `./dev skip <part|all>` opens the gate.
4. **Real-data stage (last).** `make -C project-a real-up PROJECT=utravs` shows the real Search Console data from the
   database `project_a_real` on the plan branch. The owner tests the scenarios by hand. No issues in this stage:
   a problem goes to the thread, which writes a bugfix plan `docs/devchain-plan/bugfix/bugfix-<name>.md`
   (`Status: approved` after the owner agrees), and the owner runs `./dev bugfix <name> --detach`.
5. **Missing requirements** found in the real-data stage are new rows in a plan (a new part or a bugfix plan), written
   by the thread with the owner. They are never added by Codex on its own.
6. **Review and merge.** The thread reviews the plan branch once, opens one PR `plan/<plan>` -> `main`, merges it.

## Where each database is used

| Database | Used by | Data |
|---|---|---|
| `project_a_test` | pytest, `make test` | wiped at the start of every test session |
| `project_a_qa` | `qa-up`, `./dev try`, Playwright specs | fixed seed (shop or Search Console), rebuilt on every start |
| `project_a_real` | `real-up`, `dev-api`, gsc-pusher | real pushed data; no test touches it |

The QA stack and the real stack share the UI port 5173: `make qa-down` before `real-up`. A browser that switched
between them may need Cmd+Shift+R.

## Log

- **2026-10-18** One plan, one branch: every package, QA fix and bugfix row goes on `plan/<plan>`.
- **2026-10-19** Test each part while the plan runs: `./dev try`, feedback issues, part gates, plan tree in the viewers.
- **2026-10-19** Reproduce-first: an issue's spec must fail before its fix and may not change during it; if it passes,
  the issue gets the label `question`. A scenario is required; the issue kinds are Bug, Missing, Not what I asked.
- **2026-10-19** `./dev try` has its own PostgreSQL and ClickHouse (`docker-compose.try.yml`, ports 5462 and 8143), UI 5183,
  fresh data on every try. Two seeds: shop and Search Console (`--seed`); an issue keeps its seed.
- **2026-10-19** `./dev approve all` and `skip all`. A real-data final stage with no issues, only bugfix plans.
- **2026-10-19** Bugfix rows run their browser spec; the UI smoke spec (`qa/tests/smoke/pages.spec.ts`) opens every main
  page after each UI change. Cause: P31 renamed the segment kinds and Home kept the old names; `next build` compiles
  but never opens a page, the review reads the diff, and no spec checked for a browser error.
- **2026-10-19** Next.js MCP for the agents (`.mcp.json`, `.codex/config.toml`, approval mode `approve`), so an agent
  reads the UI errors of a running dev server. A rename must grep the old name across the repo (plan template).
- **2026-10-19** `./dev bugfix`: announces every plan row, resumes the rows that never started, draws a tree in the
  viewers. A bugfix plan has no `00-overview.md`; the prompts read it only when it exists.
- **2026-10-19** `./dev web`: one fixed page, the boxes scroll, Copy JSON on the log, restarts itself when devchain
  changes on disk (it showed new pages with old data after a pull).
- **2026-10-19** Real data has its own database `project_a_real` (`real-move` copies what was pushed into the
  test database). Cause: a pytest run empties `project_a_test`, where the real data used to live.
- **2026-10-19** The segment list skips a UI row whose segment the engine no longer has, and a migration removes such
  rows. Cause: P30 deleted the old live segments; one leftover row made `/v1/segments` and `/v1/home` answer 404, and
  the UI fell back to its sample data. No QA data had an old segment, so no test saw it.
- **2026-10-20** UI rows (`UI:` in the title) get their own agent: a Sonnet designer with the `ui-ux-pro-max` skill
  writes `ui-<Pn>.md`, Codex builds it with its own prompt and a screenshot spec, and the UI review judges the
  screenshots against the spec and `docs/ui/design-system.md`. Cause: nobody designed a screen before Codex, and the
  review read only the diff, so the metric form shipped with a broken layout.
- **2026-10-21** `spec/mindset.md` holds the working agreements of the owner and PM (M01..). The preflight checks
  that every S.. and N.. the overview names reaches a row. A `spec-intake` skill for the owner's Claude project
  takes the clarify and checklist steps of GitHub Spec Kit; plans and tasks stay in devchain. Cause: questions were
  found late, in the plan check, and the owner's way of working lived only in chat threads.

## 2026-10-21 · v2 autonomous loop

`./dev run <plan>` replaces feature, bugfix, approve and skip. The tracker is the database (an issue per task);
holds, WIP, session resume, Opus triage, QA in its own worktree and the journal (`./dev log`) are described in
`docs/devchain/README.md`. Removed: part gates, `gates.md`, bugfix plans, QA fix plans.
