"""Self-improvement: which scored failures are worth an issue, and what the issue says (pure)."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_LISTED = 10
_MARKER = re.compile(r"<!-- kargah:improvement role=(?P<role>[\w-]+) -->")


@dataclass(frozen=True)
class Failure:
    scorer: str
    step_id: str
    role: str
    ticket: int
    label: str
    reason: str
    at: datetime


def failures(rows: Iterable[Mapping], own_scorers: set[str], claimed: set[tuple[str, str]]) -> list[Failure]:
    """The newest record of each (scorer, step) decides. A record without a label is a broken judge, not a failure."""
    latest = {(r["scorer"], r["step_id"]): r for r in rows}
    return [Failure(r["scorer"], r["step_id"], r["role"], r["ticket"], r["label"], r.get("reason", ""),
                    datetime.fromisoformat(r["at"]))
            for key, r in latest.items()
            if key[0] in own_scorers and key not in claimed and r["label"] and not r["passed"]]


def due(found: Sequence[Failure], threshold: int, max_age_days: int, now: datetime) -> bool:
    if not found:
        return False
    return len(found) >= threshold or min(f.at for f in found) <= now - timedelta(days=max_age_days)


def open_roles(bodies: Iterable[str]) -> set[str]:
    """Roles that already have an open improvement issue."""
    return {m["role"] for body in bodies for m in _MARKER.finditer(body)}


def issue_text(role: str, found: Sequence[Failure]) -> tuple[str, str]:
    counts: dict[str, Counter[str]] = {}
    for f in found:
        counts.setdefault(f.scorer, Counter())[f.label] += 1
    lines = [f"- {scorer}: " + ", ".join(f"{label}={n}" for label, n in sorted(c.items()))
             for scorer, c in sorted(counts.items())]
    listed = [f"- `{f.step_id}` (#{f.ticket}, {f.scorer}={f.label}): {f.reason}" for f in found[:MAX_LISTED]]
    body = "\n".join([
        f"The scorers graded {len(found)} steps of the `{role}` agent as failed.", "", "## Counts", *lines, "",
        f"## Failures (at most {MAX_LISTED})", *listed, "",
        "## What to do",
        "Change only files under `.kargah/` (agent.md, skills). For each change, name the failures it addresses. "
        "One change per failure pattern.", "", f"<!-- kargah:improvement role={role} -->"])
    return f"Factory: improve the {role} agent ({len(found)} failed scores)", body
