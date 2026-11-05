# devchain: one loop that builds a plan from tracker issues

`./dev run <plan>` is a loop. Codex builds one task at a time, a headless Claude reviews it, and the tracker (GitHub
via `gh`, or GitLab via `glab`) is the database: every task is an issue, every question and answer is a comment.
Opus triages issues and rewrites the plan; Sonnet reviews. The owner talks to the loop only through issues.
Plans: `docs/devchain-plan/` (rules: `docs/devchain-plan/README.md`). Settings: `devchain.toml`. Code: `devchain/`.
Claude.ai project instructions for the owner's chats: `docs/devchain/claude-project.md`.

## Setup on the server (once)

- `uv` (the `./dev` wrapper runs `uv run --project devchain devchain`), Codex and Claude Code logged in, `gh` (or
  `glab`) logged in, Docker, Node 20+ (`npm ci` in `project-ui/ui` and `qa`, `npx playwright install chromium`).
- `make -C project-a test-db` once (acceptance). `[forge]` in `devchain.toml` names the CLI and repo.

## Commands

```
./dev run <plan> [--detach] [--once]   # the loop; exactly one loop runs at a time (a lock in .devchain/locks)
./dev resume [plan]                    # wake a waiting loop now (SIGUSR1); starts it if it is not running
./dev stop [plan]                      # stop the loop; the current task is saved as WIP
./dev log [plan] [--task P3] [--role Build] [--errors] [-n 50] [-f]   # the journal: time  Role · item  text
./dev stats [plan]                     # per package: minutes, rounds, failed checks, cost, fix rows written later
./dev qa <suite> [S1 ...]              # QA in this tree (the loop runs it in its own worktree)
./dev try <part> [--fixed] [--seed s]  # a finished part in its own folder, ports and databases
./dev watch | web | runs | usage
```

## One round

0 lock · 1 sync (merge the plan branch and `main`, only on a clean tree) · 2 read the plan and a tracker snapshot ·
3 mirror task issues (title `P15: ...`, labels `task`, `plan:<plan>`, `part:<NN>`) · 4 read comments on task issues ·
5 triage owner issues · 6 compute holds · 7 pick · 8 build. When nothing is ready it waits `loop.poll_seconds`
(300), or until `./dev resume`.

- **Pick order:** fix row `I<n>` first, then a task that continues (WIP or just answered), then plan order.
- **Ready** = not built, its `Depends` built, nothing holds it. Holders: an open question or stuck comment, an open
  bug whose triage related it, a `WAITS FOR: #n|Pn` line from Codex (the same wait that holds nothing `loop.max_waits` times makes the task stuck). A held task holds what depends on it.
  `Touches` decides which other tasks a question or bug holds (same topic or file). Unknown `Depends` or a cycle
  hold the task and say why.
- **A question** (Codex, or the plan check when it must guess) is a comment on the task issue. Any comment from the
  owner is the answer; the task builds again with it. **Stuck** works the same: the comment is the help.
- **A limit** (Codex or Claude) is waited out. After a long wait a progress comment goes on the task issue. The
  Codex session id is kept, so the task goes on with `codex exec resume`; the work in progress is saved in
  `.devchain/wip/<plan>/<task>/` and restored if no commit touched its files meanwhile.
- **Owner comment on a task issue:** on a task not built yet it is a plan change (Opus rewrites the row and
  `trace.md` says why); on a built or closed task it is feedback (a fix row `I<n>`).
- **Owner issues** labelled `feedback`, `qa`, `plan-change` or `spec` are triaged by Opus:
  `TRIAGE: FIX | PLAN | QUESTION | NOTE`. Python rejects and undoes an edit that leaves the plan folder, changes a
  built row, or adds a fix row of more than `issues.fix_max_files` files.
- **QA:** when every task of a part with a `QA: <suite> S1 ...` line is built, a background run tests it in the QA
  worktree (`qa_worktree`: its own ports 8060/8061/5193 and databases 5472/8153). An app failure becomes an issue
  labelled `qa`; QA never fixes the app. When the fix rows of that issue are built, QA tests the scenario again: green
  comments "passes now" (you close the issue); red comments "still failing" and Opus triages it again, up to
  `qa_worktree.max_retests` fix attempts, then the `help` label. Green specs are committed between tasks.
- **Help:** a dirty tree, a conflict, a git or login problem, or 3 devchain errors in a row stop the loop and put
  the label `help` on the status issue `devchain status: <plan>`. That issue also shows the heartbeat, the current
  task, held tasks with reasons, what waits for you, and the cost.
- **Closing:** only the owner closes issues.

Every devchain comment ends with a hidden mark `<!-- devchain:<kind> ... -->`; a comment without one is a person's.
Commits carry the trailers `Package: Pn`, `Part:`, `Touches:`; they decide what is built.

## Build of one task

Codex writes the failing test, then the change (`prompts/task.md`); a changed file that is not in the row's `files`,
not a test and not in the plan folder goes back to Codex before the review (`feature.scope_ok` regex lists more); the tool runs the acceptance checks and
`loop.test_cmd`; Claude reviews; up to `loop.max_fix_rounds` fix rounds; then commit and push. When the row is
unclear Codex writes `WAITS FOR:` or a question and the plan check (Opus, `[planfix]`) either fixes the row or
the owner is asked in the issue. `[preflight]` checks every row against the code before the first task. An unresolved report blocks package mirroring, triage, QA starts and builds, including after restart. Apply owner decisions to the plan, then set the report first line to `PREFLIGHT: CLEAN` and use `./dev resume` (or start the stopped loop with `./dev run`). Comments on the status issue alone do not release this gate.

## UI rows: design, build, look

A row whose title starts with `UI:` (`| P7 | UI: metric form layout | ... |`) is a UI row. Only these rows get the
UI agent; every other row runs as above. A UI row has its own rules in each step:

| Step | Who | What |
|---|---|---|
| plan | planner | writes the row with `UI:` and its UI files; does not design. The `ui-designer` agent may write the UI spec now |
| design | UI designer (`ui.model`, Sonnet) | when `ui-<Pn>.md` is missing next to the part (`<plan>-ui-<Bn>.md` for a bugfix plan), writes it from the row, `docs/ui/design-system.md` and the `ui-ux-pro-max` skill: screen, layout, exact Persian texts, states, a `Capture` list, UX rules applied. Last line `UI SPEC: WRITTEN`, or `UI SPEC: ASK` with open questions: the tool commits the spec and stops; answer in the file, end it with `UI SPEC: WRITTEN`, `./dev resume` |
| build | Codex (`prompts/task_ui.md`) | builds the spec with the design system's tokens and classes, logical CSS for RTL, and writes `qa/tests/ui/<plan>-<pn>.spec.ts`: one test per Capture item that reaches the state, asserts its texts and saves a screenshot |
| check | the tool | UI build, smoke specs, then the row's spec in the browser (1440 x 900); no screenshot is a finding |
| review | UI review (`prompts/review_ui.md`, `ui.model`) | replaces the plain review: reads the diff, the spec and every screenshot; checks layout, texts, states, the design system, RTL and the skill's pre-delivery checklist (desktop items). `PASS`, `FIX` (back to Codex with `prompts/fix_ui.md`) or `PLAN` |

- The look is `docs/ui/design-system.md`, an owner decision. The skill (`.claude/skills/ui-ux-pro-max`, MIT,
  nextlevelbuilder/ui-ux-pro-max-skill) adds UX rules only; it never picks colours, fonts or styles, and a rule that
  conflicts with the design system or RTL Persian loses.
- Codex does not load the skill: the UI spec already carries the rules that apply, which keeps its prompt small.
- Desktop only for now. Settings: `[ui]` in `devchain.toml` (`model`, `design_system`, `skill`).
