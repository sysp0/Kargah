#!/usr/bin/env python3
"""Sum turn.completed.usage from a codex exec --json stream. Unknown lines are skipped."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: scripts/codex_usage.py <run.jsonl>", file=sys.stderr)
        return 2
    totals = dict.fromkeys(FIELDS, 0)
    try:
        lines = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        print(f"warn: {exc}", file=sys.stderr)
        return 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = event.get("usage") if isinstance(event, dict) and event.get("type") == "turn.completed" else None
        if not isinstance(usage, dict):
            continue
        for key in FIELDS:
            value = usage.get(key, 0)
            if isinstance(value, int):
                totals[key] += value
    print("\t".join(FIELDS))
    print("\t".join(str(totals[key]) for key in FIELDS))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
