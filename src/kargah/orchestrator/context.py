"""What one run knows about its ticket."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from kargah.domain.agents import AgentSpec
from kargah.domain.config import ProjectConfig
from kargah.domain.records import StepRecord
from kargah.domain.ticket import Ticket
from kargah.ports.harness import Harness


@dataclass
class Stats:
    build_rounds: int = 0
    check_fails: int = 0
    reviews: int = 0
    must_fix: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    commit: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Ctx:
    ticket: Ticket
    run: str
    bot_id: int
    cfg: ProjectConfig
    branch: str
    stats: Stats = field(default_factory=Stats)
    should_stop: Callable[[], bool] | None = None      # the owner's interrupt label, polled while an agent runs
    steps: list[StepRecord] = field(default_factory=list)      # the agent calls of this run (see recording.py)
    agents: Mapping[str, AgentSpec] = field(default_factory=dict)
    triaged: bool = False                              # triage ran in this run: it must not run twice
    harnesses: Mapping[str, Harness] = field(default_factory=dict)     # per role, wrapped to record every call

    @property
    def number(self) -> int:
        return self.ticket.number
