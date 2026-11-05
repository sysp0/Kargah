---
description: Fire-and-forget stage runner — digests PM, designs API, plans packages, implements via cheap agents, survives compact via docs/progress.md
---

# Unattended run

You are the **manager only**. Do not implement code yourself. Spawn subagents.

## Bootstrap (do once, now)
1. Create lock file `docs/UNATTENDED.lock` with one line: the user goal + PM path.
2. Reset `.claude/unattended-stop-count` to `0:0`.
3. Record base SHA: `git rev-parse HEAD` → put `Base: <sha>` in `docs/progress.md`.
4. Rewrite `docs/progress.md` Current section (≤30 lines) with:
   - Stage title / `Status: in_progress` / `Base: <sha>`
   - Goal (2–3 lines)
   - Decisions in play (only IDs + one-line quotes the user pasted)
   - `Next package: … | agent: haiku-pm-digest` with exact PM path + headings
   - Do not re-read: full PM, full spec, graphify-out/, uv.lock
5. Rely on PreCompact for `.claude/compact-handoff.md` (do not embed artifacts in chat).

## User input
$ARGUMENTS

If `$ARGUMENTS` is empty, stop and ask for: PM file path, optional section headings, slug (default `draft`), optional API out path (default `docs/api/<slug>.md`).

## Artifacts (on disk — manager passes PATHS only)
- Digest: `docs/digest/<slug>.md`
- API: `docs/api/<slug>.md` (default `docs/api/draft.md`)
- Plan: `docs/plan/<stage>.md`
Never paste file bodies into the manager context; pass paths to the next agent.

## Pipeline (one package at a time)
1. `haiku-pm-digest` — brief = PM paths/headings + digest out path → writes digest file
2. Update `docs/progress.md`
3. `api-design` — brief = digest PATH + API out path → writes API doc
4. Update `docs/progress.md`
5. `stage-planner` — brief = API PATH + decisions + plan out path → writes `docs/plan/<stage>.md`
6. For each package in the plan file (`#P1`, `#P2`, …):
   - `haiku-explorer` only if paths unknown
   - `haiku-worker` for mechanical edits | `sonnet-implementer` for logic
   - `haiku-tester` only if the implementer did not already run the acceptance command, or for batch checks
   - Any log/diff over ~200 lines → `haiku-summarizer` (do not read raw)
   - Update `docs/progress.md` after each package (`Next package: docs/plan/<stage>.md#P<n> | agent: <name>`)
7. Once per stage: `sonnet-reviewer` with brief `Base: <sha>` from progress
8. On success: `Status: done`, `Next package: none`, delete `docs/UNATTENDED.lock`

## Retry caps (per package)
- Tester fails twice → `sonnet-debugger` once → `sonnet-implementer` applies that fix once → tester
- Still failing → `Status: blocked`, details under Blockers, clear lock
- Reviewer: one fix round via implementer, **no second review**

## Hard rules
- Agents never run `git commit` or `git push`.
- Every subagent writes details to files and returns ≤15 lines. Line 1: `STATUS: ok|blocked|failed`.
- On `STATUS: blocked`, copy the `UNCLEAR:` line into Blockers, set `Status: blocked`, stop.
- Status vocabulary: `in_progress` | `done` | `blocked`.
- Never open full PM/spec in the main session.
- Never resume a finished agent; spawn fresh with a short problem list.
- After compact: read `docs/progress.md` then (if recent) `.claude/compact-handoff.md`; continue Next package only.
- English in files/terminals; unattended progress notes in English.
