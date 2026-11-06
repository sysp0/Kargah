"""What is recorded about every agent call (a "step"). Derived data: losing it loses statistics, never work."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepRecord:
    step_id: str            # f"{run}-{n:02d}"
    run: str
    ticket: int
    role: str               # triage | spec | implement | review | judge
    harness: str            # codex | claude
    model: str              # "" = the harness default
    started: str            # ISO 8601 UTC
    seconds: float
    status: str             # ok | question | limit | failed | stopped
    tokens_in: int | None
    tokens_out: int | None
    tokens_cached: int | None
    cost_usd: float | None
    cost_source: str        # reported | estimated | unknown
    base_sha: str           # sha of origin/<base> when the step started
    head_sha: str           # HEAD of the ticket branch when the step started
    schema_version: int = 1
