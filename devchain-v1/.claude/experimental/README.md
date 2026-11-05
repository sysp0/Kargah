# Experimental (not registered)

Re-enable: move `go-unattended.md` to `.claude/commands/`; move both `.py` files to `.claude/hooks/`; register PreCompact and Stop in `.claude/settings.json` with `python3` and a timeout. Rewrite the command first: it still names removed agents.

## Hardening TODOs
- Fail closed when `## Current` is missing or `Status:` is a typo.
- Anti-spin on a content hash, not mtime alone.
- Expire a stale `docs/UNATTENDED.lock`.
- Honor `stop_hook_active` so Stop cannot loop.
