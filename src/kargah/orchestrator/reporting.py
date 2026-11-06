"""`kargah report`: read the local records of a workdir and print the numbers."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from kargah.adapters.jsonl_log import read_jsonl
from kargah.domain.metrics import Report, compute
from kargah.errors import KargahError

_SPAN = re.compile(r"^(\d+)([hdw])$")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}


def parse_since(text: str, now: datetime) -> datetime | None:
    if text in ("", "all"):
        return None
    found = _SPAN.match(text)
    if not found:
        raise KargahError(f"--since must look like 12h, 7d or 2w (or 'all'), not '{text}'")
    return now - timedelta(**{_UNITS[found[2]]: int(found[1])})


def build_report(workdir: Path, since: str, now: datetime) -> Report:
    records = read_jsonl(workdir / "log.jsonl")
    runs = [r for r in records if r.get("kind", "run") == "run"]
    completions = [r for r in records if r.get("kind") == "completion"]
    return compute(runs, completions, read_jsonl(workdir / "steps.jsonl"), read_jsonl(workdir / "scores.jsonl"),
                   parse_since(since, now), now)


def format_report(report: Report) -> str:
    """One number per line: `name: value`, nested names joined with dots."""
    lines: list[str] = []

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, dict) and value:
            for key, inner in value.items():
                walk(f"{prefix}.{key}" if prefix else str(key), inner)
        else:
            lines.append(f"{prefix}: {json.dumps(value) if value in (None, {}) else value}")

    walk("", report)
    return "\n".join(lines)
