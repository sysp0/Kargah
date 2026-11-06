"""The agents of a factory: who does a role (harness, model, rights) and what it is told (pure data)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from kargah.domain.config import ProjectConfig
from kargah.domain.scoring import ScorerSpec

ROLES = ("triage", "spec", "implement", "review", "judge")      # judge steps are never scored
HARNESSES = ("codex", "claude")
ACCESS = ("read", "edit")
SIZES = ("XS", "S", "M", "L", "XL")


@dataclass(frozen=True)
class SkillRef:
    name: str
    description: str
    path: str                  # relative to the repository root


@dataclass(frozen=True)
class AgentSpec:
    role: str
    description: str
    harness: str               # codex | claude
    model: str                 # "" = the harness default
    access: str                # read | edit
    timeout_minutes: int       # 1..240
    max_budget_usd: float      # claude only; 0 = no cap
    models_by_size: Mapping[str, str]      # implement only (phase 4); {} = off
    instructions: str          # the markdown body
    skills: tuple[SkillRef, ...] = ()

    @property
    def timeout_seconds(self) -> int:
        return self.timeout_minutes * 60


@dataclass(frozen=True)
class Definition:
    """Everything the project's `.kargah/` (plus the built-in defaults) says. `problems` are "<path>: <message>"."""
    config: ProjectConfig
    agents: Mapping[str, AgentSpec]
    problems: tuple[str, ...] = field(default=())
    scorers: Mapping[str, ScorerSpec] = field(default_factory=dict)
