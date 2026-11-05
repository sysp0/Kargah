# QA loop: Claude plans scenarios, Codex writes and heals Playwright tests, Claude triages

> History: the design as decided when it was built. The current guide is `docs/devchain/README.md`; plans now live in `docs/devchain-plan/`.

Status: decided and built 2026-10-16. Runs with `./dev qa <suite>`; guide `docs/devchain.md`; first suite `docs/qa/run-metrics.md`.
Replaces package P10 of `docs/plan/run-metrics-and-segments.md`.

## Why

P10 is the end-to-end acceptance of the stage: the PM path of section 8 (send events, build metrics, run them, build segments, read reasons, change a version) must work in the real UI on real services. Unit tests and the per-package review cannot see a broken screen, a wrong label or two packages that do not fit together. P10 is therefore QA: run the scenarios, find bugs, fix them.

## Roles (same split as the code loop)

| Step | Who | Output |
|---|---|---|
| Plan scenarios | Claude (project thread) | `docs/qa/scenarios.md`: each scenario with steps, data and expected results taken only from the plan examples |
| Write tests | Codex (codex-loop) | one Playwright spec per scenario in `qa/tests/` |
| Run tests | the loop script, outside the Codex sandbox | pass/fail, `error-context.md`, screenshot and trace per failure |
| Triage | fresh headless Claude session | verdict per failure: `TEST` (the spec is wrong) or `APP` (the product is wrong), with `path:line - problem - expected` |
| Fix plan | the same triage session | `TEST` items go straight back to Codex to fix the spec. `APP` items become a fix plan `docs/plan/qa-fix-<run-id>.md` with rows F1.. (files, exact change, acceptance), in the normal plan-row format |
| Fix | Codex, through `dev feature` | implements exactly the fix rows, one review per row; then the failing scenarios run again |
| Report | Claude (project thread) | `docs/qa/report.md` with each scenario result and `docs/qa/bugs.md` with each app bug found and its fix commit |

This is the planner / generator / healer pattern of Playwright's test agents, with Claude as planner and judge and Codex as generator and healer.

## Why the script runs the browser, not Codex

Codex runs in `--sandbox workspace-write`; it cannot reach PostgreSQL, ClickHouse or the UI on 127.0.0.1. The code loop already solves this for pytest (`accept()` in `scripts/codex-loop.sh`). The QA loop does the same for Playwright: the script starts the services, runs `npx playwright test <changed spec>`, and sends the failure text back to Codex. Codex never needs network access.

## Deterministic data

Expected results must be known in advance, so QA does not use the real GSC data in `project_a_test`.
- New database `project_a_qa`, project `qa`, created and reset by `make qa-reset` before every run.
- The data is close to real but fixed (owner 2026-10-16): about 30 URLs, 13 complete weeks, daily events with realistic spread (a few large pages, many small ones, weekly rhythm, some URLs that start late or stop), generated from a fixed random seed so every reset gives the same rows. The plan example URLs are embedded with exact values so their expected results are known.
- A fixture seed `project-a/qa_seed.py` writes events whose weekly values are exactly the plan examples: URLs `/a`, `/b`, `/c`, `/d` with the clicks of section 4 (W3 120/90/70 for `/a`, ...), impressions for the CTR example of section 5, and one URL present every day for the event example. Values are generic events and attributes through the ingest API, so the seed also tests ingestion (step 1 of section 8).
- The weeks are placed relative to the run date, so "last complete week" always lands on the fixture week (the seed computes the Saturday weeks in `Asia/Tehran`).

## Layout

```
qa/
  package.json            @playwright/test pinned
  playwright.config.ts    baseURL http://localhost:5173, API http://127.0.0.1:8030, retries 0, trace and screenshot on failure, workers 1
  tests/S1-ingest-draft.spec.ts ... S7-version-change.spec.ts
  fixtures.ts             shared login/project selection and API helpers
project-a/qa_seed.py
docs/qa/scenarios.md      written by Claude
docs/qa/report.md, docs/qa/bugs.md
```

Specs use role and label locators (`getByRole`, `getByLabel` with the Persian labels from `screens.jsx`), never CSS classes or indexes, so they survive layout changes.

## Pipeline (`./dev qa`, `devchain/qa.py`)

1. Codex writes or updates the specs for the requested scenarios (prompt `qa_write.md`), never app code.
2. The tool runs `make qa-up` once, `make qa-reset`, then `npx --prefix qa playwright test <specs> --reporter=line,json`. It keeps the output tail, `test-results/**/error-context.md` (page snapshot at the failure), screenshots and traces in the run folder.
3. All pass: normal review of the specs (a spec weakened to pass is rejected: removed assertion, `test.skip`, `test.fail`, only a wider timeout), `test-fast`, commit, push.
4. Failures: a fresh Claude session (prompt `triage.md`) reads the scenario, the output and the page snapshot, may open the screenshot, and tags each failure `[TEST]` or `[APP]`. `[APP]` entries also go to `docs/qa/bugs.md` (scenario, step, expected, actual, suspected file).
5. `[TEST]` items go back to Codex (spec fix only), up to `max_fix_rounds`.
6. `[APP]` items: the triage session writes `docs/plan/qa-fix-<run-id>.md` rows (prompt `fix_plan.md`): exact files (at most 5 per row), the change, and the scenario that proves it. With `--fix auto` the tool runs those rows through the feature pipeline and then reruns the failing scenarios; with `--fix stop` it stops so the owner can read the plan first. A row that needs a product decision is written under `Blocked:` and the run stops.

## Packages

Harness and pipeline: DC4 and DC5 in `docs/plan/devchain.md`. Scenarios: `docs/qa/scenarios.md` (S1-S7 from section 8 of `docs/plan/run-metrics-and-segments.md`), written by Claude in the project thread before the first `./dev qa run-metrics S1..S7`. Report: `docs/qa/report.md` after the run.

## Decisions (owner, 2026-10-16)

1. Data: separate `project_a_qa`, fixed but close to real (see "Deterministic data").
2. The tool runs the services and the browser outside the Codex sandbox.
3. Codex does not decide fixes: it writes specs and implements fix rows; Claude triages and writes the fix plan.
4. (2026-10-17) Superseded in part by `docs/plan/qa-own-branch.md`: QA runs on the branch under test and every bug is fixed there; only decisions and large old bugs stop.
