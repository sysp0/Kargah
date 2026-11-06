"""Where the scores live, and which runs have finished (both are derived data)."""
from __future__ import annotations

from typing import Any, Protocol


class ScoreStore(Protocol):
    def scores(self) -> list[dict[str, Any]]:
        """Every score record, oldest first (a later record for the same scorer and step replaces an earlier one)."""

    def add(self, record: dict[str, Any]) -> None: ...

    def finished_runs(self) -> set[str]:
        """Ids of the runs that have ended (their run record exists)."""
