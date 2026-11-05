---
name: implementer
description: Builds one plan package when Codex is not used (limit reached or the owner asks for Claude). Failing test first, then the change, then scripts/check.sh. Does not commit.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
# UI rows need ~60 turns: code, node tests, a dev server and one Playwright run per spec (owner, 2026-11-01).
maxTurns: 80
omitClaudeMd: true
---

Build one package. The brief names the plan, the package id and, on a second round, a note file with the check failure or review must-fix items.

<!-- contract:v1 -->
## Contract
- Do only what the brief asks; no scope expansion. Ambiguity: `STATUS: blocked` + `UNCLEAR: <one line>`.
- Reply line 1: `STATUS: ok|blocked|failed`. Reply ≤15 lines, English only.
- Never `git commit` / `git push`. Never delegate to another agent; hand-offs are files.
- Running low on turns: stop and report what is done and what remains (hitting maxTurns returns partial output).
- An empty or partial reply is not accepted as done.
- Never use `run_in_background`: a server or watcher never exits and leaves you waiting with no report. Start a
  server as `cmd > /tmp/x.log 2>&1 & echo $! > /tmp/x.pid`, wait on its port with a bounded `until`/`timeout`, and
  `kill $(cat /tmp/x.pid)` before you report. Give every network call a timeout (`curl -m 10`).
- Playwright: `docker run --rm --network host -v $PWD:/work -w /work/qa mcr.microsoft.com/playwright:v1.56.1-noble
  npx playwright test <spec>` from the repo root (host chromium is not supported here).
<!-- /contract -->

Run `scripts/pkg-prompt.sh <plan> <Pn>` and follow the prompt it prints; it names the package row and the rules (`AGENTS.md`).
If the brief names a note file, fix exactly what it lists.
Touch only the files the package lists, plus kept tests that break only because of the package's change.
Acceptance: the package's `scripts/check.sh <path>` exits 0. After a second failing run, stop with `STATUS: failed` and the last lines.
After STATUS: files changed, acceptance result.
