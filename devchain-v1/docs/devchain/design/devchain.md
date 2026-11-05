# devchain: one tool for the whole development chain

> History: the design as decided when it was built. The current guide is `docs/devchain/README.md`; plans now live in `docs/devchain-plan/`.

Status: built 2026-10-16 by Claude in the project thread (owner decision: Claude builds it, Textual installed with uv, DC0 file exception accepted). User guide: `docs/devchain.md`. The package table below is the design record; the QA harness landed as `qa/`, `project-a/demo_seed/qa.py` and `project-a/scripts/qa-stack.sh`.
QA design and decisions: `docs/plan/qa-loop.md`.

## The chain (owner workflow)

1. **Shape** (owner + Claude Opus in the project thread): the owner explains the idea; Claude writes it as plan rows in `docs/plan/<stage>.md` and pushes to main.
2. **Build** (`dev feature`): on the owner's server, Codex implements each row; a fresh Claude Sonnet 5.5 session reviews each round; the tool runs acceptance and tests, commits and pushes. One branch per package.
3. **QA** (`dev qa`): Codex writes Playwright specs from the scenarios Claude wrote; the tool runs them outside the sandbox; Claude Sonnet triages failures and writes a fix plan; Codex implements exactly that plan through `dev feature`.
4. **Validate** (project thread, Claude Opus): one full review of the branch or PR against the plan, then merge.

Claude never writes product code in steps 2-3; Codex never decides what to fix.

## Commands

```bash
./dev feature <stage> <Pn>... [--branch auto|current] [--detach]   # build packages (replaces codex-loop.sh)
./dev qa <suite> [S1 ...] [--fix auto|stop] [--detach]             # write/run scenarios, triage, fix plan, fixes
./dev watch [run-id]                                                # TUI on a running or finished run (default: latest)
./dev runs                                                          # list runs: id, kind, packages, state, tokens, cost
./dev resume <run-id>                                               # continue a stopped run from its last state
./dev usage [run-id]                                                # token and cost table, plain text
```

- `--branch auto` (default): fetch main, create `codex/<pn>` from fresh `origin/main` for each package, push it, print the PR URL `https://github.com/<repo>/pull/new/codex/<pn>`. `current` keeps today's behaviour (all packages on the checked-out branch).
- `--detach`: start the run in the background (`tmux` session `dev-<run-id>` if tmux exists, else `nohup`), then open `dev watch`. Closing the TUI never stops the run.
- `--fix auto` (default for `qa`): after triage, run the fix packages at once. `stop`: write the fix plan and stop, so the owner can read it first.

## Design rules

- **Runner and viewer are separate.** The runner writes every step as one JSON line to `.devchain/runs/<run-id>/events.jsonl`; the TUI only reads that file. A crash of the TUI or a closed SSH session never stops work, and `dev watch` can attach at any time.
- **State machine per package**: `codex -> accept -> review -> build_ui -> tests -> commit -> push -> done` (or `blocked`, `failed`). Each transition is an event; `resume` restarts from the last state with the tree as it is (today's `LOOP_RESUME=1`).
- **Settings in `devchain.toml`** (repo root), not in code: models (`review_model = "claude-sonnet-5-5"`, `triage_model`), `max_fix_rounds = 3`, `review_budget_usd = 2`, test command, acceptance env (ports, DB names), QA service commands and ports, Codex flags, limit-wait defaults.
- **Prompts are files** in `devchain/prompts/` (`task.md`, `fix.md`, `review.md`, `qa_write.md`, `triage.md`, `fix_plan.md`) with `{package}`, `{plan}`, `{findings}` placeholders. Changing a prompt needs no code change. Start from the texts in `scripts/codex-loop.sh` and keep its rules block word for word.
- **Usage is recorded per call**:
  - Codex: sum of `turn.completed.usage` from `codex exec --json` (fields of `scripts/codex_usage.py`: input, cached input, cache write, output, reasoning output).
  - Claude: run `claude -p ... --output-format json` and read `usage.input_tokens`, `usage.cache_creation_input_tokens`, `usage.cache_read_input_tokens`, `usage.output_tokens`, `total_cost_usd`, `num_turns`, `duration_ms`.
  - Cache hit % = cached / (input + cached). Codex has no USD cost on a subscription; show tokens and the time spent waiting on limits.
  - Verify these field names once against the installed `codex exec --help` / `claude --help`; unknown fields are ignored, never fatal.
- **No Python dependency except the TUI**: the runner uses the standard library only; the TUI uses `textual` (needs owner approval to install, see Decisions). Without a TTY or without `textual`, `dev watch` prints a plain live summary every few seconds.
- English only in code, prompts, logs and TUI text.

## TUI (`dev watch`)

```
┌ run 20261016-2015-feature  stage run-metrics-and-segments  branch codex/p9  elapsed 00:41:12 ┐
│ Packages                         │ Usage                                                    │
│ P9   ✓ done      r1  12m  PASS   │ Codex   in 412k  cached 351k (85%)  out 38k  reason 21k  │
│ P10  ▶ review    r0   3m         │ Claude  in 9k  cache read 120k  cache write 31k  out 4k  │
│                                  │         cost $0.62   reviews 3   avg $0.21               │
│                                  │ Waiting on Codex limit: no                               │
├──────────────────────────────────┴──────────────────────────────────────────────────────────┤
│ Live: P10 round 0 review (claude-sonnet-5-5)                                                │
│ 20:52:10 accept: CHECK ok (14 tests)                                                         │
│ 20:52:41 review: reading docs/plan/run-metrics-and-segments.md:180                          │
└ q quit (run continues)  v verdict  f findings  d diff --stat  l open log  u usage table ────┘
```

Panels: package table (state, round, duration, verdict), usage (per run, per package on select), live tail of the current step, limit-wait countdown, last error. Keys open the verdict, findings, diff stat and raw logs of the selected package.

## Files

```
dev                         # 3-line shell wrapper: exec python3 -m devchain "$@"
devchain.toml
devchain/
  __main__.py  cli.py       # argparse commands
  config.py                 # read devchain.toml (tomllib)
  events.py                 # run dir, append/read events.jsonl, run index
  agents.py                 # codex exec (limit wait + resend), claude -p (json), both return text + usage
  usage.py                  # parse and sum usage
  gitops.py                 # fresh branch from origin/main, clean-tree check, commit, push
  feature.py                # package state machine (port of codex-loop.sh)
  qa.py                     # QA pipeline
  tui.py  plain.py          # viewers
  prompts/*.md
  tests/                    # fake codex/claude binaries via DEVCHAIN_CODEX_BIN / DEVCHAIN_CLAUDE_BIN; no DB, no network
.devchain/                  # run data, in .gitignore
```

## Packages (built with `scripts/codex-loop.sh devchain DC0 ...`)

| Pn | Title | files | acceptance |
|---|---|---|---|
| DC0 | Skeleton, config, events | `dev`, `devchain/__main__.py`, `devchain/cli.py`, `devchain/config.py`, `devchain/events.py` (+ `devchain.toml`, `.gitignore` line, `devchain/tests/test_events.py`; owner exception: up to 8 files) | `./dev runs` lists two runs written by the test; events append and read back in order; missing `devchain.toml` gives a clear error |
| DC1 | Agents and usage | `devchain/agents.py`, `devchain/usage.py`, `devchain/tests/test_agents.py`, `devchain/tests/fakes/` | fake codex prints `turn.completed` usage and a limit message once: the call waits (wait shortened by config in the test), resends, and returns summed usage; fake claude JSON gives tokens and cost; unknown fields ignored |
| DC2 | Feature pipeline | `devchain/feature.py`, `devchain/gitops.py`, `devchain/prompts/{task,fix,review}.md`, `devchain/tests/test_feature.py` | with fakes and a temp git repo: PASS path commits and records `done`; FIX path sends findings back and stops after `max_fix_rounds`; `Blocked:` in progress stops with `blocked`; `resume` continues from `review`; `--branch auto` creates `codex/<pn>` from `origin/main` |
| DC3 | Viewers | `devchain/tui.py`, `devchain/plain.py`, `devchain/tests/test_plain.py` | `dev watch --plain` on a recorded events file prints package states and usage totals; the Textual app renders the same model (Textual `run_test` pilot if `textual` is installed, else skipped) |
| DC4 | QA harness | `qa/package.json`, `qa/playwright.config.ts`, `qa/tests/smoke.spec.ts`, `project-a/Makefile` (`qa-up`, `qa-reset`), `project-a/qa_seed.py` | `docs/plan/qa-loop.md` section "Deterministic data"; `make qa-reset` twice gives identical data; smoke spec passes |
| DC5 | QA pipeline | `devchain/qa.py`, `devchain/prompts/{qa_write,triage,fix_plan}.md`, `devchain/tests/test_qa.py` | with fakes: a failing spec gives a triage verdict; `[TEST]` items go back to Codex; `[APP]` items become a fix plan `docs/plan/qa-fix-<run-id>.md` with rows F1..; `--fix auto` runs them through the feature pipeline, `--fix stop` stops after writing it |
| DC6 | Switch over | `scripts/codex-loop.sh` (becomes `exec ./dev feature --branch current "$@"`), `docs/plan/codex-loop.md`, `docs/plan/thread-workflow.md`, new `docs/devchain.md` (user guide) | old command still works; guide shows every command with an example |

DC0-DC3 can run while QA scenarios are being written. After DC6, every new stage runs with `./dev feature`.

## Decisions (owner)

1. Who builds devchain: Codex through the current `codex-loop.sh`, packages DC0-DC6 (recommended: cheapest, same review as product code), or Claude in the project thread directly.
2. TUI library: `textual` installed on the server with `python3 -m pip install textual` (recommended), or plain text only.
