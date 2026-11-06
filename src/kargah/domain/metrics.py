"""The dashboard numbers, computed from the local records only (pure; no API call)."""
from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any

Report = dict[str, Any]
Rec = dict[str, Any]


def _t(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _between(rows: Sequence[Rec], key: str, since: datetime | None, now: datetime) -> list[Rec]:
    return [r for r in rows if (when := _t(r.get(key))) and (since is None or since <= when) and when <= now]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _gap(rows: Sequence[Rec], start: str, end: str) -> float | None:
    """Median seconds from one timestamp to another, over the rows that have both."""
    return _median([(_t(r[end]) - _t(r[start])).total_seconds() for r in rows if r.get(start) and r.get(end)])


def compute(runs: Sequence[Rec], completions: Sequence[Rec], steps: Sequence[Rec], scores: Sequence[Rec],
            since: datetime | None, now: datetime) -> Report:
    in_runs = _between(runs, "started", since, now)
    in_steps = _between(steps, "started", since, now)
    merged = [c for c in _between(completions, "merged_at", since, now) if c["outcome"] == "merged"]
    handoffs = {r["ticket"] for r in in_runs if r["outcome"] == "needs-human"}
    interactions = [c["human_interactions"] for c in merged]
    return {
        "runs": dict(Counter(r["outcome"] for r in in_runs)),
        "steps_by_role": dict(Counter(s["role"] for s in in_steps)),
        "handoffs": len(handoffs),
        "merged": len(merged),
        "merge_rate": len(merged) / len(handoffs) if handoffs else None,
        "autonomy": sum(1 for c in merged if not c["human_pushed"]) / len(merged) if merged else None,
        "human_interactions_per_mr": {"mean": statistics.mean(interactions) if interactions else None,
                                      "median": _median(interactions)},
        "cycle": {"kickoff_to_handoff": _gap(merged, "kickoff_at", "handoff_at"),
                  "handoff_to_first_review": _gap(merged, "handoff_at", "first_human_review_at"),
                  "first_review_to_merge": _gap(merged, "first_human_review_at", "merged_at"),
                  "kickoff_to_merge": _gap(merged, "kickoff_at", "merged_at")},
        **_costs(merged, steps, in_steps),
        "scorers": _scorers(scores),
        "improvement_acceptance": _improvement(_between(completions, "kickoff_at", since, now)),
    }


def _costs(merged: Sequence[Rec], all_steps: Sequence[Rec], in_steps: Sequence[Rec]) -> Report:
    tickets = {c["ticket"] for c in merged}
    per_mr = [sum(s["cost_usd"] or 0.0 for s in all_steps if s["ticket"] == t) for t in sorted(tickets)]
    by_role: Counter = Counter()
    for s in in_steps:
        by_role[s["role"]] += s["cost_usd"] or 0.0
    median = _median(per_mr)
    return {"cost_per_mr": {"median": round(median, 6) if median is not None else None,
                            "steps_unknown_cost": sum(1 for s in all_steps if s["ticket"] in tickets
                                                      and s["cost_usd"] is None)},
            "cost_by_role": {role: round(cost, 6) for role, cost in by_role.items()}}


def _scorers(scores: Sequence[Rec]) -> Report:
    latest: dict[tuple[str, str], Rec] = {}
    for r in scores:                       # a later record for the same (scorer, step) replaces the earlier one
        latest[(r["scorer"], r["step_id"])] = r
    out: Report = {}
    for scorer in sorted({k[0] for k in latest}):
        mine = [r for (name, _), r in latest.items() if name == scorer]
        out[scorer] = {"count": len(mine), "pass_rate": sum(1 for r in mine if r["passed"]) / len(mine),
                       "labels": dict(Counter(r["label"] for r in mine))}
    return out


def _improvement(completions: Sequence[Rec]) -> float | None:
    closed = [c for c in completions if "factory-change" in c.get("labels", [])]
    return sum(1 for c in closed if c["outcome"] == "merged") / len(closed) if closed else None
