Rules: English only in code, comments, terminal output, commits and repo docs. No Search Console names
(clicks, impressions, position, ctr, gsc, page_url) under project-a/app/engine/. Numbers and limits live in
DB settings or seeds, not in code. New rules go into project-a/app/engine, not only demo_api. Do not change
gsc-developer-reference/. Do not change decisions in spec/decisions.md. Do not implement per-project retention
or retention editing (docs/backlog.md B7).
No new logic: build only the behaviour the row and spec/ state. A rule, condition, default, threshold, error case,
event or field that neither states is new logic: never invent it, stop with the plan-problem note instead.
You cannot reach PostgreSQL, ClickHouse or the UI from your sandbox. That is never a reason to write Blocked:. The
tool runs the migrations, tests and browser checks for you and sends the exact errors back; fix from the error
text alone. Use Blocked: only for a problem in the plan or the spec, never for a tool or sandbox limit.
Tests live in project-a/app/tests/ and project-a/demo_api/tests/: grep both for kept tests. A test you add
must run and must fail without the change: no `pytest.importorskip`, `skip` or `skipif`, and no assert that holds
either way. project-a/app/tests cannot import demo_api or demo_seed, so a test of a demo_api route or service,
or of demo_seed, goes in project-a/demo_api/tests/ (a removed route answers 404, or 405 when another method shares its path).
spec/ decides behaviour, never a test: kept tests may be older than spec/. When a kept test fails and its assert is
what spec/ and the row ask, fix the code, never the test. Change a kept test's assert only where the row changes
that behaviour, and only to what the row and spec/ state; do it in the same change as the code, before any check.
When the `graphify` command exists, find code with `graphify query "<question>"` or `graphify explain <name>`
before grepping; never open the files in graphify-out/ directly.
