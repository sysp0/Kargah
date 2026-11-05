#!/usr/bin/env python3
"""Require exactly the four Claude agents, with one contract."""
from __future__ import annotations

import sys
from pathlib import Path

EXPECTED = ("implementer.md", "planner.md", "reviewer.md", "ui-designer.md")
MODELS = {"implementer.md": "sonnet", "planner.md": "sonnet", "reviewer.md": "sonnet", "ui-designer.md": "sonnet"}
KEYS = ("name:", "description:", "tools:", "model:", "maxTurns:")
CONTRACT = """<!-- contract:v1 -->
## Contract
- Do only what the brief asks; no scope expansion. Ambiguity: `STATUS: blocked` + `UNCLEAR: <one line>`.
- Reply line 1: `STATUS: ok|blocked|failed`. Reply ≤15 lines, English only.
- Never `git commit` / `git push`. Never delegate to another agent; hand-offs are files.
- Running low on turns: stop and report what is done and what remains (hitting maxTurns returns partial output).
- An empty or partial reply is not accepted as done.
<!-- /contract -->
"""


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    return parts[1]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    agents = root / ".claude" / "agents"
    found = tuple(sorted(p.name for p in agents.glob("*.md")))
    if found != EXPECTED:
        print(f"agents: expected {list(EXPECTED)}, found {list(found)}")
        return 1
    for name in EXPECTED:
        text = (agents / name).read_text(encoding="utf-8")
        fm = frontmatter(text)
        missing = [key for key in KEYS if key not in fm]
        if missing:
            print(f"{name}: missing {', '.join(missing)}")
            return 1
        if f"model: {MODELS[name]}" not in fm:
            print(f"{name}: model must be {MODELS[name]}")
            return 1
        if CONTRACT not in text:
            print(f"{name}: contract block mismatch")
            return 1
    print(f"agents ok ({len(EXPECTED)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
