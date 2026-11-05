#!/usr/bin/env python3
"""SessionStart: inject restore pointer only when unattended or after compact/resume."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
PROGRESS = ROOT / "docs" / "progress.md"
HANDOFF = ROOT / ".claude" / "compact-handoff.md"
LOCK = ROOT / "docs" / "UNATTENDED.lock"
LAST_COMPACT = ROOT / ".claude" / "last-compact.json"
HANDOFF_MAX_AGE_S = 6 * 3600


def main() -> int:
    # Drop legacy stamp if present
    LAST_COMPACT.unlink(missing_ok=True)

    raw = sys.stdin.read().strip()
    source = "startup"
    try:
        payload = json.loads(raw) if raw else {}
        source = payload.get("source") or source
    except json.JSONDecodeError:
        pass

    if not LOCK.is_file() and source not in ("compact", "resume"):
        return 0

    lines = [
        "TOKEN-SAFE RESTORE:",
        f"- SessionStart source: {source}",
        "- Read ONLY docs/progress.md first (≤30 lines).",
    ]
    if HANDOFF.is_file():
        try:
            age = time.time() - HANDOFF.stat().st_mtime
        except OSError:
            age = HANDOFF_MAX_AGE_S + 1
        if age <= HANDOFF_MAX_AGE_S:
            lines.append("- Then read .claude/compact-handoff.md (recent compact snapshot).")
    lines.extend(
        [
            "- Do NOT re-read full PM/spec/graphify-out/uv.lock.",
            "- Manager only: brief subagents with PATHS; never paste file bodies.",
            "- Roles: read AGENTS.md; implement only the package from scripts/pkg-prompt.sh; update Pkgs:; do not commit.",
            "- After every package: update docs/progress.md before starting the next.",
        ]
    )
    if not PROGRESS.is_file():
        lines.append("- WARNING: docs/progress.md missing — create it before continuing.")

    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines),
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
