---
description: Write a plan folder for one feature from spec ids or a short topic, then ask the open questions
argument-hint: <topic and spec ids, e.g. "segment export N57 S24-S26"> [hard]
---
# /plan
$ARGUMENTS — a topic plus the spec ids it implements. If empty, ask and stop.
1. Call `planner` once with PATHS only (`spec/README.md`, the spec ids, `spec/mindset.md`, `docs/devchain-plan/README.md`). Model opus only if the arguments say `hard`.
2. An empty or partial reply is not done. Check that the Open questions cover each new stored concept (where stored, who sets it, how often sent, ClickHouse change) and that an ingest/upload row has a realistic-size test and an early dry/real-data run; if not, ask the planner once more.
3. Set `Plan:`, `Base:` (`git rev-parse HEAD`) and a line `P1 next` under `## Current` in `docs/progress.md`.
4. Show the plan path and one line per package. Ask every Open question in the chat (AskUserQuestion when it has options), write the answers into `00-overview.md`, and stop. No code.
