"""The coding agent behind a role (build, review). Codex and Claude are adapters; the factory knows neither."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class HarnessRequest:
    role: str                  # "build" or "review"
    prompt: str
    cwd: Path
    timeout_seconds: int
    model: str = ""
    should_stop: Callable[[], bool] | None = None   # polled while the agent runs; True = stop it now


@dataclass(frozen=True)
class HarnessResult:
    ok: bool
    text: str = ""
    limited: bool = False                      # the agent hit a usage limit
    resets_at: datetime | None = None          # read from the agent's own message, never guessed
    error: str = ""
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cached: int | None = None
    stopped: bool = False                      # the factory stopped the agent (should_stop)


class Harness(Protocol):
    name: str                 # "codex" | "claude"; recorded with every step

    def run(self, request: HarnessRequest) -> HarnessResult: ...
