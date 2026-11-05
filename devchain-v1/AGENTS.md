# project-a

General Metric / Event / Segment / Action engine. GSC is only the first adapter.

## Essentials
- `spec/` wins. Start at `spec/README.md`; decisions in `spec/decisions.md`, PM scenarios in `spec/scenarios.md`.
- If code and spec truly contradict, stop. Do not guess.
- Words: `spec/glossary.md` defines every term (Entity, Attribute, Metric, Segment, ...). Our meaning wins over WebEngage, PostHog and old docs. A word missing there, or used another way: stop and ask.
- `gsc-developer-reference/` is a reference. Do not change it.
- Tests and demos use database `project_a_test`. Secrets live only in `.env`.
- Commands: `make up`, `make test`, `make demo`.
- Rules: `docs/RULES.md`. GSC names under `app/engine/**` are scanned. Thresholds belong in the DB.
- English only in code, comments, terminal output, and repo docs.
- UI errors: Next's MCP (`next-devtools` in `.mcp.json`; Codex gets it from devchain.toml) reads a running dev server.
  Auto-discovery may find nothing: call `nextjs_call` with `port` (QA stack 5173, `./dev try` 5183, real-up 5173)
  and `toolName` `get_errors` (needs the page open in a browser) or `compile_route`. Details:
  `project-ui/ui/AGENTS.md`.

## Principle: change-fast code (owner, 2026-10-18)
- Build only what the next 3 months need. Nobody knows this product 6 months from now.
- Write code we can change in hours: small modules, clear boundaries, definitions and numbers in the DB, tests for important behaviour, no abstraction before a second real use.
- When a design grows (extra option, rare case, future-proofing), ask: who needs it, when, and what breaks without it? No clear answer means leave it out.
- Ship, let the PM test, improve. Speed of change beats completeness.

## Production logs (Grafana)
- Slow or failing routes: read Grafana through the `OWNER` plugin tools (`mcp__plugin_OWNER_grafana__*`), read-only. Workflow and LogQL: `spec/infra/logging.md` (section «دسترسی Agent به Grafana»). Loki datasource uid `ffwu9etsiz3swb`, always select `{stack="marketing"}`.
- Never log bodies, headers, tokens, emails or SQL text. Use `engine.logs.get_logger(module)`; no `print(` or `logging.getLogger` (rule 4 in `docs/RULES.md`).

## Check
- Acceptance is `scripts/check.sh [path]`. It stops at the first failure (repo rules, ruff if configured, pytest).
- Pass: `CHECK ok (N tests)`. Fail: at most 10 lines, exit 1.
- `project-a/` paths run in docker compose (no host DB needed). Keep load light: `N=2` workers and `nice -n 10` are the
  defaults (`make test`, `check.sh`); do not raise `N` or run the full suites in parallel.
- Browser specs: `make -C project-a e2e SPEC=tests/<dir>/<name>.spec.ts [REAL=1]` (docker Playwright; host chromium is unsupported).

## Package
- Read `AGENTS.md`, `docs/progress.md`, and only package `Pn` in its plan part `docs/devchain-plan/<plan>/NN-*.md` (plus the `00-overview.md` sections it names).
- Do not read other packages or full PM docs.
- Start by writing the failing test, then the change.
- Touch only the files listed in the package (`files` ≤ 5), plus kept tests that break only because of the
  package's change (fix them, do not stop; the task prompt says how).
- `scripts/pkg-prompt.sh <stage> <Pn>` prints this prompt.

## Temporary containers
- Any test or one-off container (ClickHouse, Postgres, ingest, Playwright, ...) is started with `docker run --rm` (compose: `docker compose run --rm`) and anonymous volumes are removed with it. A container that cannot use `--rm` (for example `-d`) is stopped with `docker rm -f -v <name>`. Leaving containers or volumes on the server uses its disk.
- After a task, check `docker ps -a` and `docker volume ls -f dangling=true` for what you left behind.

## No N+1 queries
- Production incident 2026-11-02: `POST /v1/segments/{id}/run` took 67 s for about 800 members because it ran 2,477 Postgres queries (one or more per member or per column). The UI proxy gave up after 30 s and showed «مشکلی در سرور پیش آمد».
- The number of queries a request or run makes must not grow with the number of rows (members, entities, events, columns). Never run a query inside a loop over rows. Fetch with one `WHERE key = ANY(%s)` query, or write with `executemany` / `INSERT ... SELECT`, then group in Python.
- A package that reads or writes many rows adds a test with a realistic size (about 800 rows or more) that counts queries (wrapper on `pg.execute`, as in `app/tests/test_system_user.py`) and asserts a small fixed bound. It must fail on the loop version.
- Check your route in Grafana after deploy: `db_queries` in the `http_request` line (spec/infra/logging.md). More than about 30 queries or more than 1 s of `db_ms` for a list route is a bug to fix, not a note.

## Non-interactive
- You cannot ask questions. On ambiguity, or after a second failing acceptance run, STOP.
- Write the question or the failure under `Blocked:` in `docs/progress.md` `## Current`.
- Do not guess. Do not widen scope.

## Done
- The package acceptance command exits 0.
- Only listed files changed.
- A one-line entry for the package under `## Current` in `docs/progress.md` is added.

## Git
- Never edit a committed migration; add a new one. An uncommitted migration may be edited. If a migration checksum guard refuses a test database, run `make test-db-reset` from `project-a/` to drop and re-migrate `project_a_test` and all its `gw*` databases. This deletes test data only.
- Never commit. Never push.

## Report
- End with a summary of at most 10 lines: files changed, acceptance result, what is next.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
