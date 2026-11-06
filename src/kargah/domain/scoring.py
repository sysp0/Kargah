"""Scorers: judge agents that grade a step after the fact. Sampling is a hash, so it is repeatable (pure)."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreLabel:
    value: str
    score: float
    description: str


@dataclass(frozen=True)
class ScorerSpec:
    name: str
    description: str
    agents: tuple[str, ...]            # roles whose steps it grades
    harness: str
    model: str
    passing_score: float
    sampling_rate: float               # percent, 0..100; 0 = manual scoring only
    self_improvement: bool
    labels: tuple[ScoreLabel, ...]
    instructions: str


def sampled(step_id: str, scorer: str, rate: float) -> bool:
    """Deterministic: the same step is always (not) chosen for the same scorer and rate."""
    h = int(hashlib.sha256(f"{scorer}:{step_id}".encode()).hexdigest()[:8], 16)
    return h % 10_000 < round(rate * 100)


def parse_judgement(text: str, labels: Sequence[ScoreLabel]) -> tuple[str, str] | None:
    """(label, reason) from the last `LABEL:` line naming a known label; the reason may be empty. Else None."""
    known = {label.value for label in labels}
    chosen = [v for v in (m.strip() for m in re.findall(r"^LABEL:\s*(.+)$", text, re.M)) if v in known]
    if not chosen:
        return None
    reasons = re.findall(r"^REASON:\s*(.+(?:\n(?!LABEL:|REASON:).+)*)", text, re.M)
    return chosen[-1], reasons[-1].strip() if reasons else ""


def score_of(spec: ScorerSpec, label: str) -> float:
    return next(item.score for item in spec.labels if item.value == label)
