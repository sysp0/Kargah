# Engineering standards (Python)

Kargah is a public tool other people will run on their repositories. Treat it as a product, not a script.

## Layout (ports and adapters)
```
src/kargah/
  domain/        pure data and rules: Ticket, Task, Run, Outcome, Label. No I/O, no imports from other layers.
  ports/         Protocols only: Tracker, GitHost, Harness, Clock, LogSink. The factory depends on these.
  adapters/      gitlab/, github/, codex/, claude/, fs/. The only place that calls subprocess, HTTP or the disk.
  tasks/         one module per task (implement, review, rework): a task is a small class using ports.
  orchestrator/  picks the next run from the tracker and starts it. Knows tasks only through a registry.
  cli/           thin entry points; parse arguments, build the objects, call the orchestrator.
tests/           mirrors src/; fakes in tests/fakes implement the ports.
```
Legacy v1 modules (`loop.py`, `feature.py`, `forge.py` ...) sit flat in `src/kargah/` and are replaced piece by piece (strangler); new code goes into the layout above.

## Rules
1. **One reason to change per module** (SRP). Hard limit 300 lines per file, 40 per function; enforced by `tests/test_structure.py` (legacy files are capped at today's size and may only shrink).
2. **Depend on ports, not adapters** (DIP). Constructors take their collaborators; no module-level singletons, no hidden `subprocess` calls outside `adapters/`.
3. **Open for extension** (OCP): a new tracker, harness or task is a new module plus one registry line, not an edit to the orchestrator.
4. **Small interfaces** (ISP): a port has only the methods its user needs (e.g. `IssueReader` and `IssueWriter` rather than one `Tracker` with twenty methods, if they differ in users).
5. **Substitutable adapters** (LSP): every adapter passes the same contract test suite as the fake.
6. Type hints everywhere; `ruff` (lint + format) and a type checker in CI; no bare `except`; errors are typed (`KargahError` subclasses).
7. Every new task needs its five-question table (docs/tasks/<name>.md) and a test before it merges.
8. No secrets in logs or `log.jsonl`; the bot token lives only in the engine process.
