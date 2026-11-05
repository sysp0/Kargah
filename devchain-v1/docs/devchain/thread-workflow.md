# How a project thread drives the plan packages

Owner workflow since 2026-10-16, updated 2026-10-18 for plan folders. Give this file to a new Claude thread so it can
continue without the old thread.

## Roles
- Owner: runs `./dev` on their own server, pulls main, tells the thread when a run ends.
- Codex: writes the code for one package through devchain (`./dev run <plan>`, guide `docs/devchain/README.md`). Inside the run a fresh Claude Sonnet session reviews each round; the tool runs the acceptance check and `test-fast`, commits and pushes the branch.
- QA: `./dev qa <suite>` writes and runs Playwright specs for `docs/qa/<suite>.md`, triages failures and writes a fix plan.
- Testing while the plan runs: each finished part stops the run (`[feature] gate`); the owner or the PM tests it with
  `./dev try <part>` and files GitHub issues with the `feedback` form; the run turns them into rows `I<n>` and builds
  them before the next package (guide: `docs/devchain/README.md`, "Test each part while the plan goes on"). An issue
  labelled `decide` comes to the thread: change the plan or `spec/`, then remove the label.
- Project thread Claude: writes the plan, reviews the pushed branch against it, opens and merges the PR, and writes doc changes. It never runs `./dev` and never edits product code unless the owner asks in so many words.

## One plan, one branch (owner rule, 2026-10-18)
A branch is a plan, not a feature. Every package, QA fix and bugfix row of a plan goes on `plan/<plan>`.
1. Owner, on the server:
   ```bash
   git checkout main && git pull --no-rebase --no-edit origin main
   ./dev run <YYYY-MM-DD-name> --detach          # the loop: every task in order on plan/<plan>
   ```
2. A plan problem stops the run with `docs/devchain-plan/<plan>/blocked-<Pn>.md` (pushed on the plan branch). The owner
   gives it to the thread. The thread reads it from `origin/plan/<plan>`, pushes the plan fix to `plan/<plan>` (the
   plan check fixes rows there too) and `spec/` fixes to `main` (never `docs/progress.md` while the plan runs), and
   says "fixed". The owner runs `./dev resume`; it merges `origin/plan/<plan>` and `main` in. A fix pushed to
   `plan/<plan>` while a run is still going is merged by the run's next push.
3. After a part, the owner runs its QA on the same branch: `git checkout plan/<plan> && ./dev qa <suite> S1 S2 ...`.
4. When the plan is done (or at a part the owner names), the thread reviews the whole branch once:
   - `git diff --stat origin/main...origin/plan/<plan>`, then the hunks per package commit (`git log` trailer
     `Package: Pn`) against its row; tests that cover each acceptance; no GSC names under `app/engine/`; no decision in
     `spec/decisions.md` broken; docs and code say the same thing.
   - The thread has no databases; it trusts the loop's acceptance and test-fast runs and says so.
5. Right: the thread opens one PR `plan/<plan>` -> `main` and merges it (merge commit), then updates `docs/progress.md`.
   Gaps: a fix row `P<n>a` under the package in the part file on `main`; the loop reads the changed row on its next round
   (it merges `main` into the plan branch first, so the new row is there, and skips the packages already done).
6. The thread replies in Persian, short: verdict, PR link, and the exact commands for the next step.

## Rules the thread keeps
- Doc, plan and spec changes go straight to `main`, no PR, except a fix to a plan that is running: that goes to
  `plan/<plan>`. The owner pulls with `git pull --no-rebase --no-edit origin <branch>`.
- Repo docs are English except `spec/` (Persian); chat with the owner is Persian.
- Ambiguity in the plan: ask the owner, do not guess. Do not change a decision in `spec/decisions.md` without the owner.
- Build only what the next 3 months need (`spec/README.md`).

## Where state lives
- `spec/`: product truth (decisions, glossary, scenarios, rules).
- `docs/progress.md`: which plan is current, which packages are done and what is next.
- `docs/devchain-plan/<YYYY-MM-DD>-<name>/`: the work list and contracts.
- `docs/devchain/README.md`: how `./dev` works (feature, QA, viewer) and its settings (`devchain.toml`).
- `docs/devchain/process-log.md`: the owner's flow today, which database each stack uses, and every change to the flow with its cause. Add a line there with each change.
- `docs/backlog.md`: follow-ups. Every important future item goes here with a priority (P1 critical .. P4 low), a category, a numeric example, and how to build it.

## Starting a new phase (read this first in a fresh thread)
1. The owner explains what changed. The thread asks questions where the design gets heavy and records the answers in `spec/`. PM scenarios go to `spec/scenarios.md` with expected numbers.
2. The thread writes a plan folder from `docs/devchain-plan/_template/`: parts in run order, rows Pn (at most 5 files, a named test), and no open questions left.
3. The owner builds on the server with `./dev run <plan>`, watches with `./dev watch`, tells the thread "done".
4. The thread reviews the plan branch against the plan, opens one PR, merges, updates `docs/progress.md`.
5. QA: the thread writes `docs/qa/<suite>.md` scenarios; the loop tests a finished part in its own worktree and files app failures as issues labelled `qa`, which Opus triages into fix rows. The owner comments on task issues; the loop answers there.
