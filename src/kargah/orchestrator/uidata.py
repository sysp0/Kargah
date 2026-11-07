"""What the local UI shows: plain dicts built from the workdir's derived files (log, steps, scores, bench)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from kargah.adapters.jsonl_log import read_jsonl
from kargah.domain.bench import recommend, summarize
from kargah.orchestrator.reporting import build_report, parse_since


def _day(stamp: str) -> str:
    return stamp[:10]


def dashboard(workdir: Path, since: str, now: datetime) -> dict[str, Any]:
    start = parse_since(since, now)
    keep = (lambda stamp: True) if start is None else (lambda stamp: datetime.fromisoformat(stamp) >= start)
    cost: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for step in read_jsonl(workdir / "steps.jsonl"):
        if keep(step["started"]) and step.get("cost_usd"):
            cost[_day(step["started"])][step["role"]] += step["cost_usd"]
    outcomes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for run in _runs(workdir):
        if keep(run["started"]):
            outcomes[_day(run["started"])][run["outcome"]] += 1
    return {"report": build_report(workdir, since, now),
            "cost_by_day": [{"day": d, "total": round(sum(r.values()), 6), "by_role": dict(r)}
                            for d, r in sorted(cost.items())],
            "runs_by_day": [{"day": d, "count": sum(o.values()), "outcomes": dict(o)}
                            for d, o in sorted(outcomes.items())]}


def _runs(workdir: Path) -> list[dict[str, Any]]:
    return [r for r in read_jsonl(workdir / "log.jsonl") if r.get("kind", "run") == "run"]


def runs(workdir: Path, limit: int = 50) -> list[dict[str, Any]]:
    """The newest runs first, each with the agent calls (steps) it made."""
    steps: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in read_jsonl(workdir / "steps.jsonl"):
        steps[s["run"]].append({k: s.get(k) for k in ("step_id", "role", "harness", "model", "started", "seconds",
                                                       "status", "cost_usd")})
    newest = sorted(_runs(workdir), key=lambda r: r["started"], reverse=True)[:limit]
    return [{**{k: r.get(k) for k in ("run", "ticket", "outcome", "started", "seconds", "cost_usd")},
             "steps": sorted(steps.get(r["run"], []), key=lambda s: s["started"])} for r in newest]


def scorers(workdir: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in read_jsonl(workdir / "scores.jsonl"):
        latest[(r["scorer"], r["step_id"])] = r
    by_scorer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in latest.values():
        by_scorer[r["scorer"]].append(r)
    out = []
    for name, rows in sorted(by_scorer.items()):
        days: dict[str, list[bool]] = defaultdict(list)
        for r in rows:
            days[_day(r["at"])].append(bool(r["passed"]))
        out.append({"scorer": name, "count": len(rows), "passed": sum(1 for r in rows if r["passed"]),
                    "by_day": [{"day": d, "rate": sum(v) / len(v), "count": len(v)} for d, v in sorted(days.items())],
                    "failures": [{k: r.get(k) for k in ("step_id", "ticket", "role", "label", "reason", "at")}
                                 for r in sorted(rows, key=lambda r: r["step_id"]) if not r["passed"]][:10]})
    return out


def improvements(workdir: Path) -> list[dict[str, Any]]:
    return [{"issue": r["issue"], "role": r["role"], "failures": len(r.get("score_keys", []))}
            for r in read_jsonl(workdir / "log.jsonl") if r.get("kind") == "improvement"]


def benchmarks(workdir: Path) -> list[dict[str, Any]]:
    by_suite: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in read_jsonl(workdir / "bench" / "results.jsonl"):
        by_suite[r["suite"]].append(r)
    out = []
    for suite, rows in sorted(by_suite.items()):
        summaries = summarize(rows)
        out.append({"suite": suite, "recommended": recommend(summaries), "summaries": [asdict(s) for s in summaries]})
    return out
