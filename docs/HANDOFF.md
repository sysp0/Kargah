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
uv run --with pytest pytest -q                       # 156 pass, 3 live skipped
set -a; . /opt/infra/plugin/private/sandbox-bot.env; set +a
uv run --with pytest pytest -q tests/test_tracker_contract.py   # live contract (needs `glab` login as owner)
# one factory pass (label an issue `ready` in the sandbox first):
uv run python -m kargah.orchestrator.cli run --workdir /opt/infra/plugin/sandbox-run --once                      # Codex builds
uv run python -m kargah.orchestrator.cli run --workdir /opt/infra/plugin/sandbox-run --once --builder claude --build-model claude-sonnet-5-5
```
Outcomes printed: `needs-human | question | limit | limit-unknown | blocked | interrupted | idle | busy`.

## What is done (verified)
Label state machine; engine with run lock and crash recovery from tracker+git; build (test first, check, **proof = new tests must fail on base**), independent review, rework (max 2), WIP draft commits (`Kargah-State: incomplete`) on limit/question/interrupt, auto-resume time read from the agent's own message, `/decision` files, `log.jsonl`, GitLab issue+MR adapter, bot-loop guard, token isolation. Live: Codex limit parsed correctly (issue #6 waits until 02:24 UTC 2026-11-06); full cycle with Claude builder reached `needs-human` (issue #8, MR !2). Details and bugs found: `first-run.fa.md`.

## Decisions made (owner)
Option A (real factory) · GitLab first, tracker-agnostic ports · label-driven UX (no mention needed) · one run at a time · bot role Developer, no push to `main` · one ticket = one task for now · only the owner creates tickets (backlog: factory-created) · plan with many tasks = parent issue + one child per task, `publish` idempotent via hidden `plan-id/task-id` (NOT built yet) · `/decision` comments become project files · Codex/Claude limit = auto-continue using parsed time, else label by owner · review must never be skipped when Claude is limited · idelop group and bot-in-group: later (personal namespace for now; group project access tokens are refused by GitLab) · size/SOLID rules are for this repo only, never imposed on user projects · GitLab history is unimportant, only GitHub matters.

## Not done / known risks
1. Codex as builder on a full ticket not yet run (limited until 02:24 UTC); only its limit path is proven.
2. `publish` (plan file to parent+child issues), `blocks`-style dependencies (GitLab `blocks` needs a paid plan; the engine must enforce `Depends:` itself), plugin (`init`, inventory, `retro`, `/rate`) not built. `INSTALL.md` is a draft.
3. Interrupt only checked between steps, not inside a running agent.
4. `watch` mode (long-running loop) untested; only `--once` run live.
5. Claude-as-builder runs with a tool allowlist, no hard sandbox: review before using on real projects.
6. Proof treats any non-zero exit as "fails on base" (shortcut in `tasks/proof.py`).
7. Reviewer cannot run `check.sh` in its sandbox; the engine runs it, but reviews are read-only judgments.
8. Per-run cost recorded minimally (`log.jsonl` has tokens and review cost; Codex cost not captured).
9. Sandbox leftovers: issue #6 (limit evidence), #7 (blocked, draft MR !1), #8 (needs-human, MR !2); stale probe bot user in the sandbox. Delete freely.
10. Secrets: nothing secret is in the repo (checked); keep it so.

## Plan v2 (2026-11-06, Warp Factories review)
`docs/warp-review.fa.md` = PM analysis of Warp Factories and the gap table; `docs/plan-v2.fa.md` = the phased logic plan (phases 0-9), one step per Sonnet session. Phase 0 there = steps 1-2, 4-5 below. The steps below stay valid; plan-v2 orders and details them.

## Next steps (in order)
1. After 02:24 UTC: run the factory with Codex on a fresh `ready` issue in the sandbox; confirm WIP-commit/resume with a real Codex run; record the result in `first-run.fa.md`.
2. Run `--watch` (no `--once`) for a while on the sandbox with 2-3 tickets: check idle polling, ordering, limit wait, the lock; fix what breaks.
3. Build `publish`: plan file `docs/plans/<date>-<name>/plan.md` (rows: id, title, Depends, acceptance test, at most 5 files, layer) to parent issue with checklist + child issues (`relates_to`), idempotent; the engine enforces `Depends`.
4. Make interrupt effective inside long agent runs (poll the label while the agent runs; terminate and WIP-commit).
5. Hardening: stricter proof (tell collection errors from real failures), Claude-builder sandbox, per-run caps on time/tokens, capture Codex usage.
6. Add the invariants contract (`.kargah/invariants/`, exit 77 = skip) as in `invariants.fa.md`, run before `check`.
7. Plugin layer: `/kargah init` (inventory per INSTALL.md), `/kargah publish`, `retro` (Matt's 7 categories) fed by `log.jsonl`.
8. Then, not before: run on marketing-os using its real contract (`/opt/infra/plugin/private/inventory-marketing-os.md`; open unknowns: Makefile recipes, `qa-stack.sh`, `.env` provisioning); decide the bot account for the idelop group.
9. Later (backlog): factory-created tickets, GitHub/Linear adapters, disposable runners, eval/benchmark, retire legacy modules and remove their size caps.

## Working agreements for the next session
Persian replies, simple, with a concrete scenario for any new concept; ask only when blocked; tests before claims; never print tokens; do not push history rewrites without being told; report honestly what was not verified.
