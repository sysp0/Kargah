#!/usr/bin/env python3
"""Stop: if unattended run is active and Status is in_progress, continue the next package.

Activated only when docs/UNATTENDED.lock exists (created by /go-unattended).
Counter file format: count:progress_mtime_ns. Anti-spin if progress.md mtime unchanged.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
LOCK = ROOT / "docs" / "UNATTENDED.lock"
PROGRESS = ROOT / "docs" / "progress.md"
COUNTER = ROOT / ".claude" / "unattended-stop-count"
MAX_CONTINUES = int(os.environ.get("UNATTENDED_MAX_CONTINUES", "12"))

STATUS_RE = re.compile(r"(?im)^\s*Status:\s*(\S+)\s*$")


def read_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def current_section(text: str) -> str:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "## current":
            start = i + 1
            break
    if start is None:
        return text
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## ") and lines[j].strip().lower() != "## current":
            end = j
            break
    return "\n".join(lines[start:end])


def parse_status(text: str) -> str | None:
    section = current_section(text)
    m = STATUS_RE.search(section)
    if not m:
        return None
    return m.group(1).strip().lower()


def read_counter() -> tuple[int, int]:
    if not COUNTER.is_file():
        return 0, 0
    raw = COUNTER.read_text(encoding="utf-8").strip()
    if ":" in raw:
        left, right = raw.split(":", 1)
        try:
            return int(left or "0"), int(right or "0")
        except ValueError:
            return 0, 0
    try:
        return int(raw or "0"), 0
    except ValueError:
        return 0, 0


def write_counter(count: int, mtime_ns: int) -> None:
    COUNTER.parent.mkdir(parents=True, exist_ok=True)
    COUNTER.write_text(f"{count}:{mtime_ns}\n", encoding="utf-8")


def clear_lock(message: str) -> int:
    LOCK.unlink(missing_ok=True)
    write_counter(0, 0)
    sys.stdout.write(json.dumps({"systemMessage": message}))
    return 0


def main() -> int:
    _ = read_payload()

    if not LOCK.is_file():
        return 0

    count, prev_mtime = read_counter()
    if count >= MAX_CONTINUES:
        return clear_lock(
            "Unattended stop cap reached; removed docs/UNATTENDED.lock. "
            "Re-run /go-unattended to continue."
        )

    if not PROGRESS.is_file():
        return clear_lock(
            "docs/progress.md missing; removed docs/UNATTENDED.lock."
        )

    try:
        text = PROGRESS.read_text(encoding="utf-8", errors="replace")
        mtime_ns = PROGRESS.stat().st_mtime_ns
    except OSError:
        return clear_lock(
            "docs/progress.md unreadable; removed docs/UNATTENDED.lock."
        )

    status = parse_status(text)
    if status != "in_progress":
        return clear_lock(
            f"Unattended stopped (Status: {status or 'unparsable'}). "
            "Cleared docs/UNATTENDED.lock."
        )

    if count > 0 and prev_mtime and mtime_ns == prev_mtime:
        return clear_lock(
            "Unattended anti-spin: docs/progress.md mtime unchanged since last "
            "continue; removed docs/UNATTENDED.lock. Update progress.md and re-run."
        )

    write_counter(count + 1, mtime_ns)
    reason = (
        "Unattended mode is ON (docs/UNATTENDED.lock). "
        "Before stopping: (1) update docs/progress.md (Status / Next package / Blockers), "
        "(2) run ONLY the Next package via the named subagent (pass PATHS, do not paste files), "
        "(3) do not re-read full PM/spec. "
        f"Continue count {count + 1}/{MAX_CONTINUES}."
    )
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
