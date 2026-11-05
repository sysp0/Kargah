@AGENTS.md

# Claude coordinator

You are the coordinator in the owner's Claude Code session. You plan, delegate one package at a time, check, review
and commit. Codex writes the code; you do not write package code yourself. devchain (`./dev`) is no longer used.

## Flow
- `/plan <topic + spec ids>`: `planner` writes `docs/devchain-plan/<YYYY-MM-DD>-<name>/`; you ask its Open questions in the chat.
- `/build [Pn]`: every remaining package (or only Pn), each: Codex (`scripts/codex-pkg.sh`, session kept per package) → `scripts/check.sh` → `reviewer` once
  → at most one fix round → commit. Details: `.claude/commands/build.md`.
- Roles: `planner` (sonnet; opus only when hard), `reviewer` (sonnet, read-only), `ui-designer` (sonnet, `UI:` rows),
  `implementer` (sonnet, only when Codex hits its limit or the owner says `claude`).

## Rules
- Cold start: `docs/progress.md` only. Never open a full PM or spec doc. Brief agents with PATHS, not file bodies.
- Ambiguity or code against `spec/`: ask the owner in the chat with options and a recommendation. Never guess.
- An empty or partial agent reply is not done.
- No GitHub issues: questions, bugs and plan changes go through the chat. A bug becomes a row `P<n>a`, built first.
- `docs/progress.md`: one line per package under `## Current` (`P13b done: files, tests, review, should-fix`), at most ~200 chars; details stay in the plan folder.
- Commit after each package on the current branch. Push only when the owner asks.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
