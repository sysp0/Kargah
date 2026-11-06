# HANDOFF: state of Kargah at the end of session 1 (2026-11-06)

Read this first in a new session. Language of docs: Persian (`*.fa.md`) for the owner, English for code and INSTALL.

## Goal (owner's words, short)
A public **software factory** (not an assistant) that works through tracker issues, for any project; the owner talks to it only in issue comments; a bot identity writes; Matt Pocock's vocabulary (task, trigger, run, runner, slots, brakes, 5 questions) and Zach Lloyd's requirements (factory as code, durable orchestrator, measurement, tracker/harness swappable, no secrets for agents). The owner is new to the concepts: go step by step, explain with concrete scenarios, every step needs "done means", an automated test and a visible trace. First real project to run on: marketing-os (later); first test project: the sandbox.

## Where things are
| What | Where |
| --- | --- |
| Repo (local) | `/opt/infra/plugin/kargah` (remotes: `github` = git@github.com:sysp0/Kargah.git, public, source of truth; `origin` = GitLab idelop-community/plugin/kargah, private, **stale history, ignore**) |
| Sandbox project (GitLab, personal, private) | https://gitlab.com/sysp0/kargah-sandbox (project id 88573447); local clone `/opt/infra/plugin/kargah-sandbox` |
| Factory working dir for runs | `/opt/infra/plugin/sandbox-run` (`repo/`, `state/run.lock`, `log.jsonl`) |
| Bot token (sandbox only, Developer, expires 2026-12-05) | `/opt/infra/plugin/private/sandbox-bot.env` (0600, **never commit or print**) |
| Private inventory of the real project (real names) | `/opt/infra/plugin/private/inventory-marketing-os.md` (outside the public repo on purpose) |
| References (third-party clones) | `/opt/infra/plugin/reference-mattpocock-skills`, `/opt/infra/plugin/references/zazencodes-season-3` |
| Owner's real project | `/opt/infra/apps/marketing-os` (its `./dev` loop is retired; active flow = `/plan` and `/build` slash commands) |

## Docs map (`docs/`)
`PRD.fa.md` (v0.1, superseded) then `PRD.v0.2.fa.md` (decisions) · `architecture-A.fa.md` (**main design**: engine + plugin, issue-only interface, bot identity, WIP commits, limits, cost, GitLab findings, plan to issues) · `tasks.fa.md` (5 questions for implement/review/rework, labels, rules) · `invariants.fa.md` (project-owned checks contract, draft) · `project-dependencies.fa.md` (ledger of project-specific dependencies) · `factory-v1.fa.md`, `two-systems.fa.md`, `decision-evolve-or-rebuild.fa.md` (analysis of old devchain; note the correction banner) · `research.fa.md` and `references.md` (Matt, Gumloop, zazencodes, Zach Lloyd) · `engineering-standards.md` (applies only to this repo) · `backlog.fa.md` · `first-run.fa.md` (live evidence) · root `INSTALL.md` (agent install guide, DRAFT).

## Code map (`src/kargah`)
New (clean layers, files at most 300 lines): `domain/` (ticket, markers, inputs = bot-loop guard, decision, stages, review, config) · `ports/` (tracker, http, harness, workspace, githost, shell, logsink) · `adapters/` (gitlab tracker and MR, git workspace, codex, claude, shell, env cleaner, limits parser, toml config, jsonl log) · `tasks/` (build, review, proof, decisions, prompts/*.md) · `orchestrator/` (engine, run, lock, progress, texts, services, cli).
Legacy v1 (flat modules `loop.py`, `feature.py`, `forge.py`, `cli.py`, `tui.py`, `web.py`, ...; `tasks.py` was renamed `plan_tasks.py`): kept only until replaced; line caps in `tests/test_structure.py` may only go down.

## How to run
```bash
cd /opt/infra/plugin/kargah
uv run --with pytest pytest -q                       # 337 pass, 4 live skipped (about 4 minutes)
set -a; . /opt/infra/plugin/private/sandbox-bot.env; set +a
uv run --with pytest pytest -q tests/test_tracker_contract.py   # live contract (needs `glab` login as owner)
# one factory pass (label an issue `ready` in the sandbox first):
uv run python -m kargah.orchestrator.cli run --workdir /opt/infra/plugin/sandbox-run --once                      # Codex builds
uv run python -m kargah.orchestrator.cli run --workdir /opt/infra/plugin/sandbox-run --once --builder claude --build-model claude-sonnet-5-5
```
Outcomes printed: `needs-human | question | limit | limit-unknown | blocked | interrupted | idle | busy`.

## What is done (verified)
Label state machine; engine with run lock and crash recovery from tracker+git; build (test first, check, **proof = new tests must fail on base**), independent review, rework (max 2), WIP draft commits (`Kargah-State: incomplete`) on limit/question/interrupt, auto-resume time read from the agent's own message, `/decision` files, `log.jsonl`, GitLab issue+MR adapter, bot-loop guard, token isolation. Live: Codex limit parsed correctly (issue #6 waits until 02:24 UTC 2026-11-06); full cycle with Claude builder reached `needs-human` (issue #8, MR !2). Details and bugs found: `first-run.fa.md`.
Plan v2 steps done (2026-11-06): **0.4** proof: the new tests must pass on the change and fail on base with an exit code in `proof.fail_codes` (default `[1, 2]`; another code = broken run, rejected) (`tests/test_proof.py`). **2.1** (part): `.kargah/config.toml` is read only from `origin/HEAD` via `Workspace.read_default`, never from the ticket branch; a build that changes `.kargah/` fails its gate unless the ticket has label `factory-change` (`tests/test_definition_guard.py`). `FileSource` (`DirSource`, `DefaultBranchSource`, `Workspace.list_default`, `load_project_config(source)`) done 2026-11-06 (`tests/test_file_sources.py`). Deviation: `run.py` still loads the config twice (before and after `prepare`), both from `origin/HEAD`: `prepare` needs `base_branch` and the fetch can bring a newer default branch.

**Item 6 (2026-11-06):** when the build is done, nothing changed and HEAD is `Kargah-State: incomplete`, the engine makes an empty commit with `Kargah-State: complete` (`Workspace.commit(allow_empty=True)`, `TicketRun._close_wip`); test `test_resume_after_a_question_with_no_new_change_completes_the_wip_commit`.

**0.3 (2026-11-06):** interrupt works inside a running agent. `adapters/process.py::run_stoppable` (process group, SIGTERM then SIGKILL after 10 s), `HarnessRequest.should_stop` / `HarnessResult.stopped`, `orchestrator/interrupt.py::InterruptWatch` (asks the tracker at most every 30 s), build and review both stop -> WIP commit + `needs-info`. Tests: `tests/test_process.py`, `test_harness_stop.py`, `test_interrupt_watch.py`, two engine tests in `test_engine.py`. Plan note: the reviewer is stoppable too (not only the builder).

**1.1 (2026-11-06):** `domain/records.py::StepRecord`, `ports/runstore.py::RunStore`, `adapters/fs_runstore.py::FsRunStore` (`runs/<run>/<step>/…`, `steps.jsonl`, modes 0700/0600, `prune` by the record's `started`). Tests: `tests/test_runstore.py`.

**1.2 (2026-11-06):** every harness call is a step: `orchestrator/recording.py::RecordingHarness`, `domain/pricing.py::step_cost` (reported/estimated/unknown), `Workspace.base_sha/diff`, `HarnessResult.tokens_cached`, `Harness.name`, config `[pricing."<model>"]` and `[runs] keep_days`, prune at the start of `Engine.tick`. `log.jsonl` run records now carry `kind`, `steps`, `cost_usd`, `cost_unknown_steps`. Tests: `test_pricing`, `test_recording`, `test_config_pricing`, `test_workspace_diff`, two in `test_engine`.

**2.2 (2026-11-06):** agents and skills as files. Defaults in `src/kargah/defaults/agents/{implement,review}/agent.md` (TOML frontmatter `+++`), project overrides in `.kargah/agents/<role>/agent.md` and skills in `.kargah/skills/`, `adapters/factory_files.py::load_definition`, `adapters/harness_factory.py::make_harness`, `domain/agents.py`, `tasks/prompting.py::compose`. `ProjectConfig` lost the model and timeout keys (now `[check] timeout_seconds` only); `Services` has `harness_for` and `load_definition`. `--builder/--build-model` override the files. Tests: `tests/test_definition.py`. Existing sandbox config has no `[models]`, so nothing breaks there.

**2.3 (2026-11-06):** `kargah.orchestrator.cli validate --repo PATH` (one problem per line, exit 1) and `Engine.tick` returns `config-error: <first problem>` without touching any ticket; `Workspace.refresh()` runs first in every tick (one `git fetch` per poll). Tests: `tests/test_validate.py`.

**Phase 3 (2026-11-06):** full ticket life. `domain/handoff.py::decide_handoff` (6 rules, `/revise` + open diff threads), `orchestrator/closing.py::Closer` (complete -> `done` label + closed issue + `kind: completion` record; cancel), `orchestrator/feedback.py` (durable `feedback` comment, thread resolve, no duplicate `ready`), `Progress.feedback_sha/feedback_open/reviews_since_feedback`, `GitHost.find_mr/open_discussions/resolve_discussion/mr_notes/commit_authors`, `Tracker.close_ticket/include_closed`, `Engine._settle_handoffs` runs before agent work, safe point in `_drive` (interrupt, closed issue, merged MR). Bugs found by self-review are listed in plan-v2 phase 3. Tests: `test_handoff`, `test_feedback_stage`, `test_lifecycle` (+ githost adapter and tracker contract).

**Phase 4 (2026-11-06):** triage, spec and the approval gate. `domain/triage.py`, `domain/stages.py` (10-rule table, `Policy`, `SpecView`), `tasks/triage.py`, `tasks/spec.py`, `orchestrator/planning.py`, defaults `defaults/agents/{triage,spec}/agent.md`, label `needs-approval`, config `[stages]`, `models_by_size` router (`tasks/prompting.py::sized_agent`). Not done: 4.7 (optional `DECIDE`). Tests: `test_triage`, `test_stages`, `test_planning`, `test_workspace_diff::task_commits`.

**Phase 5 (2026-11-06):** `kargah.orchestrator.cli inbox [--json]` (`domain/inbox.py`, `orchestrator/inbox.py`; oldest-waiting first) and `report --workdir DIR [--since 7d|all] [--json]` (`domain/metrics.py::compute`, `orchestrator/reporting.py`). Pure and local: reads `log.jsonl`, `steps.jsonl`, `scores.jsonl`. Tests: `tests/test_metrics_inbox.py`; also run once on the sandbox.

**Phase 6 (2026-11-06):** scorers. `.kargah/scorers/<name>/scorer.md` + built-in `task-compliance` and `review-quality` (both `sampling_rate = 0`), `domain/scoring.py` (hash sampling, judgement parser), `adapters/scorer_files.py`, `ports/scorestore.py` + `adapters/fs_scores.py` (`scores.jsonl`), `orchestrator/scoring.py::Scoring` (max 3 per tick, after the main work; judge runs in an empty temp dir; invalid answer twice -> record with `label: null`; usage limit -> no record), CLI `score`. Tests: `test_scorers`, `test_scoring_run`. Not run live (no cost spent on judges).

## Decisions made (owner)
Option A (real factory) · GitLab first, tracker-agnostic ports · label-driven UX (no mention needed) · one run at a time · bot role Developer, no push to `main` · one ticket = one task for now · only the owner creates tickets (backlog: factory-created) · plan with many tasks = parent issue + one child per task, `publish` idempotent via hidden `plan-id/task-id` (NOT built yet) · `/decision` comments become project files · Codex/Claude limit = auto-continue using parsed time, else label by owner · review must never be skipped when Claude is limited · idelop group and bot-in-group: later (personal namespace for now; group project access tokens are refused by GitLab) · size/SOLID rules are for this repo only, never imposed on user projects · GitLab history is unimportant, only GitHub matters.

**Phase 8 (2026-11-06):** benchmarks. `.kargah/benchmarks/<suite>/{suite.toml,tasks/*.toml}` (`adapters/bench_files.py`, validated by `kargah validate`), `domain/bench.py` (summary and recommendation: best correctness, ties within 0.05 go to the cheaper), `orchestrator/bench.py::BenchRunner` (one git worktree per trial at an exact commit, same `RunLock`, results in `<workdir>/bench/results.jsonl`), CLI `bench run SUITE --workdir DIR [--config NAME]` and `bench add-task --suite S --from-step ID --workdir DIR [--repo PATH]`. Tests with fakes only; not run live. Phases 7 and 9 wait for the owner's B2 decision.

## Spec approval (owner decided 2026-11-06)
GitLab swallows a `/approve` comment on issues, so the owner approves a spec by adding the label `approved` (`Label.APPROVED`). The label wins over comments; a `/approve` comment still works on trackers that keep it. The label is removed when the ticket completes or is cancelled. Tests: `test_planning::test_the_approved_label_...`.

## Not done / known risks
1. Codex as builder on a full ticket not yet run (limited until 02:24 UTC); only its limit path is proven.
2. `publish` (plan file to parent+child issues), `blocks`-style dependencies (GitLab `blocks` needs a paid plan; the engine must enforce `Depends:` itself), plugin (`init`, inventory, `retro`, `/rate`) not built. `INSTALL.md` is a draft.
3. ~~Interrupt only checked between steps~~ fixed by 0.3.
4. `watch` mode (long-running loop) untested; only `--once` run live.
5. Claude-as-builder runs with a tool allowlist, no hard sandbox: review before using on real projects.
6. ~~Resume after a question blocks when the builder changes nothing~~ fixed (see "What is done").
7. Reviewer cannot run `check.sh` in its sandbox; the engine runs it, but reviews are read-only judgments.
8. Per-run cost recorded minimally (`log.jsonl` has tokens and review cost; Codex cost not captured).
9. Sandbox leftovers: issue #6 (limit evidence), #7 (blocked, draft MR !1), #8 (needs-human, MR !2); stale probe bot user in the sandbox. Delete freely.
10. Secrets: nothing secret is in the repo (checked); keep it so.

## Plan v2 (2026-11-06, Warp Factories review)
`docs/warp-review.fa.md` = PM analysis of Warp Factories and the gap table; `docs/plan-v2.fa.md` = the phased logic plan (phases 0-9), one step per Sonnet session. Phase 0 there = steps 1-2, 4-5 below. The steps below stay valid; plan-v2 orders and details them.

## Next steps (in order)
1. (done) spec approval by label `approved`.
2. Owner decides B2 (factory-created issues, never `ready`); then phases 7 (self-improvement) and 9 (cron automation) of `docs/plan-v2.fa.md`.
3. Run `--watch` (no `--once`) for 30 minutes on the sandbox with 2-3 tickets (plan 0.2, not done); try a live `bench run` and a live scorer (`sampling_rate` > 0) with a few cents of budget.
4. Optional 4.7 (`DECIDE:` findings in a review) and the invariants contract (`invariants.fa.md`).
5. `publish` (plan file to parent and child issues), then the plugin layer (`init`, `retro`).
6. Then, not before: marketing-os with its real contract (`/opt/infra/plugin/private/inventory-marketing-os.md`).
7. Backlog: factory-created tickets, GitHub/Linear adapters, disposable runners, retire legacy modules and their size caps.

## Working agreements for the next session
Persian replies, simple, with a concrete scenario for any new concept; ask only when blocked; tests before claims; never print tokens; do not push history rewrites without being told; report honestly what was not verified.
