# References

Material for design sessions. Local clones live **outside** this repo in `/opt/infra/plugin/references*` (third-party, not vendored here).

| Source | What it is | Use for |
| --- | --- | --- |
| [mattpocock/skills PR #1316](https://github.com/mattpocock/skills/pull/1316), [`software-factory` skill](https://github.com/mattpocock/skills/tree/main/skills/in-progress/software-factory) | Shared vocabulary: task, trigger, run, runner; services (ticket tracker, ticket source, git host, orchestrator, observability). "Start slow", "fill every slot", "question every task" (5 questions). Surveys per slot + `EXAMPLE-TASKS.md`. Local: `/opt/infra/plugin/reference-mattpocock-skills/skills/in-progress/software-factory/` | The language and the design checklist of Kargah |
| [mattpocock/skills](https://github.com/mattpocock/skills), [changelog v1.3](https://www.aihero.dev/skills/skills-changelog-v13-implement-spec-pr-retro-and-glossary-md) | Skill collection (`claude plugins install mattpocock-skills`); implement-spec, PR, retro, glossary | Ideas for skills, retro, glossary |
| [Gumloop: Software Factory](https://www.gumloop.com/engineering/software-factory) (2026-10-29) | Production factory from telemetry: evidence-backed PRs, tests fail before the fix and pass after, no auto-merge, review queue, 83% merged without human edits | Metrics to measure, "proof with every PR" |
| [zazencodes software-factory-claude-code-v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2) | Small Claude Code factory on GitHub issues: label `factory` -> intake -> spec -> build -> gate (`checks.sh`) -> reviewers -> approver. Install via `INSTALL.md`. Local: `/opt/infra/plugin/references/zazencodes-season-3/` | Closest small, readable example of a plugin-style factory |
| Zach Lloyd (Warp) thread, 2026-11 (PDF, not vendored) | A factory is not "a string of prompts": it needs (1) factory-as-code (prompts, workflows, runners, integrations, evals), (2) a durable orchestrator (resume after a crash without duplicate work, humans can steer/hand off), (3) data, measurement, audit logs, self-improvement | The long-term target; why logs and `/retro` matter |

Re-check "surveyed 2026-10" claims in the slot surveys (prices, betas) before relying on them.
