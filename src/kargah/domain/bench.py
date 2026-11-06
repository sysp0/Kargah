"""Benchmarks: which configurations (harness + model) do a set of fixed tasks best (pure)."""
from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

TIE = 0.05           # correctness closer than this counts as equal; then the cheaper configuration wins


@dataclass(frozen=True)
class Configuration:
    name: str
    harness: str
    model: str


@dataclass(frozen=True)
class BenchTask:
    name: str
    title: str
    body: str
    success_criteria: str
    start_sha: str               # a full 40-character commit id; a branch or tag would drift
    source_step: str = ""


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    role: str
    repetitions: int
    scorers: tuple[str, ...]
    configurations: tuple[Configuration, ...]
    tasks: tuple[BenchTask, ...]
    definition_hash: str         # of the suite and task files: an edited suite makes old results incomparable


@dataclass(frozen=True)
class Summary:
    configuration: str
    n: int
    mean_correctness: float
    pass_rate: float             # trials with correctness == 1
    mean_cost: float | None
    median_seconds: float


def summarize(results: Sequence[dict[str, Any]]) -> list[Summary]:
    by_config: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_config[r["configuration"]].append(r)
    out = []
    for name, rows in sorted(by_config.items()):
        correct = [r["correctness"] or 0.0 for r in rows]
        costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
        out.append(Summary(name, len(rows), statistics.mean(correct), sum(1 for c in correct if c == 1) / len(rows),
                           statistics.mean(costs) if costs else None, statistics.median(r["seconds"] for r in rows)))
    return out


def recommend(summaries: Sequence[Summary]) -> str | None:
    """The best mean correctness; configurations within TIE of it are equal, and then the cheapest wins."""
    if not summaries:
        return None
    best = max(s.mean_correctness for s in summaries)
    close = [s for s in summaries if best - s.mean_correctness <= TIE]
    return min(close, key=lambda s: (s.mean_cost if s.mean_cost is not None else float("inf"),
                                     -s.mean_correctness, s.configuration)).configuration
