# Install Kargah into a project

> **DRAFT.** The plugin files this guide copies do not exist yet (roadmap phase 2). Steps 0, 1 and 4 are real and
> usable now as a dry run (they only read the project and write `.kargah/inventory.md`). Steps 2 and 3 are placeholders.

You are a coding agent installing Kargah into the user's project. Work in the project root. Do not clone this repository.

**The rule of this guide: look first, then ask, never guess.** Kargah is generic; the project is not. Every project has
dependencies Kargah cannot see from here: make targets, compose stacks, ports, databases, seeded data, untracked files,
repo-specific rules and tests. You must find them, show them to the user, and record them. Anything you cannot find is
recorded as `unknown` and asked, not assumed.

## 0. Check the project

Stop and tell the user if any of these fail:

- It is a git repo with an `origin`. Detect the host from `git remote get-url origin`: GitHub (`gh auth status`) or
  GitLab (`glab auth status`). Both must be able to create labels and issues. Other hosts: stop and say so.
- The default branch exists on `origin`.
- `claude --version` and the build agent's CLI (default `codex --version`) run. `uv --version` and `python3 --version`
  (3.11+) run.
- No Kargah files exist yet (`.kargah/`, `kargah.toml`). If one does, show the clash and ask before overwriting.

## 1. Inventory (do this before copying anything)

Read, in this order, whatever exists: `AGENTS.md`, `CLAUDE.md`, `README*`, `Makefile`, `package.json` scripts,
`pyproject.toml`, `docker-compose*.yml`, `.env.example`, CI config (`.github/workflows`, `.gitlab-ci.yml`), `scripts/`,
and the `tests/` entries that test the repo itself rather than the product (for example a test that inspects `make -n`
output or greps source for forbidden words).

Write `.kargah/inventory.md` with one row per finding, using the kinds in
[docs/project-dependencies.fa.md](docs/project-dependencies.fa.md): `hook`, `invariant`, `link`, `env`, `tool`, `rule`,
`skill`. Columns: `kind | what | where found | status (found | assumed | unknown) | question for the user`.

Always look for these and write a row even if the answer is "none found":

| Look for | Why |
| --- | --- |
| How to run the project's checks, per layer (`api`, `ui`, `core`), non-interactively and without rewriting files | becomes `check.sh` |
| Setup needed before tests (database, images, containers) | `hooks.setup`; a stale image or missing DB fails every job |
| Rules enforced by the repo itself (custom lints, tests that inspect the repo, forbidden names) | `invariants`: these must run before a package is accepted |
| Services the app needs (database, queue, search) and the ports they use | `hooks.stack.*` and `env`; ports must not clash with the user's dev stack |
| Files that are not in git but a fresh worktree needs (`.env`, `node_modules`, credentials files) | `links`; record names only |
| Environment variable **names** the tests read | `env`; **never record or print values** |
| Tools that must be installed (docker, make, playwright, language toolchains) | `tools` |
| How the project deploys, if at all | optional `hooks.deploy` |
| Layers present (`api`, `ui`, `core`, any subset) | `layers` in config |

Do not run anything that changes state (no `make test-db`, no `docker compose up`) during the inventory. Reading and
`make -n` are fine.

## 2. Show the user the inventory and the gaps

Print a short summary: counts by status, then every `unknown` and every `assumed` row as a question. Then a section
titled **Gaps: what Kargah cannot see from here** listing anything you found a reference to but could not follow
(a script that is not in the repo, a `make` target whose recipe you could not read, a service that needs credentials).
Wait for answers and update `inventory.md`. Do not continue while an `unknown` row blocks a check.

## 3. Copy and configure (placeholder until the plugin exists)

1. Install the plugin (`/plugin install kargah`) and run `/kargah init`, which creates `.kargah/config.toml`, an empty
   `.kargah/log.jsonl`, the `.gitignore` entries and the layer `AGENTS.md` skeletons from the inventory. It must never
   overwrite an existing file.
2. Turn each inventory row into config: hooks and links into `.kargah/config.toml`, invariants into
   `.kargah/invariants/`, rules into the project's `AGENTS.md`, tools into the checks of step 4.
3. `scripts/check.sh`: no arguments runs every layer, `--layer <name>` runs one, output at most 10 lines, exit code zero
   only on success. Non-interactive; never `--fix`, never update snapshots.

## 4. Verify

1. Every `tool` row resolves (`command -v`).
2. `scripts/check.sh` exits 0 on the default branch. If it fails there, no job can ever pass: tell the user what is
   broken; do not edit the project to make it pass.
3. Every invariant runs and exits 0 on the default branch.
4. No secret value appears in `.kargah/` or in any file you wrote (`grep` for the names you recorded).
5. `git status` shows only intended files, and `.kargah/state/` is ignored.

## 5. Hand over

Stay on the user's current branch. Commit with a one-line message, show the diff, ask before pushing. Then tell the user,
in a few lines: what was found, what is still `unknown`, how to start (`/kargah plan`, then `/kargah build`), and that
nothing merges without a human.
