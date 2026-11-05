#!/usr/bin/env python3
"""PreCompact: write a small handoff from the last ~200KB of the transcript.

No API calls. No progress.md embed. Cap ~2500 chars.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
HANDOFF = ROOT / ".claude" / "compact-handoff.md"
TAIL_BYTES = 200_000
MAX_ASSISTANT = 3
MAX_CHARS_EACH = 600
MAX_HANDOFF = 2500
GIT_LINES = 30
GIT_TIMEOUT = 5


def read_stdin() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text") or "")
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def read_transcript_tail(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > TAIL_BYTES:
                fh.seek(-TAIL_BYTES, os.SEEK_END)
            data = fh.read()
        text = data.decode("utf-8", errors="replace")
        # Drop partial first line if we seeked mid-file
        if size > TAIL_BYTES:
            nl = text.find("\n")
            if nl >= 0:
                text = text[nl + 1 :]
        return text
    except OSError:
        return ""


def scrape_assistants(blob: str) -> list[str]:
    assistants: list[str] = []
    for line in blob.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = row.get("role") or row.get("type")
        msg = row.get("message") if isinstance(row.get("message"), dict) else row
        if role in ("assistant", "ai") or msg.get("role") == "assistant":
            text = extract_text(msg.get("content")).strip()
            if text:
                # keep tail of each turn
                assistants.append(text[-MAX_CHARS_EACH:])
    return assistants[-MAX_ASSISTANT:]


def git_cap(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "(unavailable)"
    out = (proc.stdout or "").strip() or "(empty)"
    lines = out.splitlines()[:GIT_LINES]
    return "\n".join(lines) if lines else "(empty)"


def main() -> int:
    payload = read_stdin()
    session_id = payload.get("session_id") or "unknown"
    trigger = payload.get("trigger") or "unknown"
    transcript = payload.get("transcript_path") or ""
    cwd = payload.get("cwd") or str(ROOT)

    assistants = scrape_assistants(read_transcript_tail(Path(transcript))) if transcript else []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    HANDOFF.parent.mkdir(parents=True, exist_ok=True)

    parts = [
        "# Compact handoff (auto)",
        f"- Written: `{now}`",
        f"- Trigger: `{trigger}`",
        f"- Session: `{session_id}`",
        f"- Cwd: `{cwd}`",
        "",
        "## Resume",
        "1. Read `docs/progress.md`.",
        "2. Continue only **Next package** (pass PATHS; do not re-open PM/spec).",
        "",
        "## git status --short",
        git_cap(["git", "status", "--short"]),
        "",
        "## git diff --stat",
        git_cap(["git", "diff", "--stat"]),
        "",
        "## Recent assistant turns (tail)",
    ]
    if assistants:
        for i, a in enumerate(assistants, 1):
            parts.append(f"### A{i}")
            parts.append(a)
    else:
        parts.append("(none)")

    body = "\n".join(parts).strip() + "\n"
    if len(body) > MAX_HANDOFF:
        body = body[: MAX_HANDOFF - 20].rstrip() + "\n…[truncated]\n"

    HANDOFF.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
