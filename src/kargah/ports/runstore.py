"""Where step records and their artifacts (prompt, reply, diff, ticket text) are kept."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from kargah.domain.records import StepRecord


class RunStore(Protocol):
    def save_step(self, record: StepRecord, artifacts: Mapping[str, str]) -> None:
        """Append the record and write each artifact (file name -> text)."""

    def steps(self) -> list[StepRecord]:
        """All records, oldest first."""

    def artifact(self, step_id: str, name: str) -> str | None: ...

    def prune(self, older_than: datetime) -> int:
        """Delete the artifact folders of steps started before the given time (records stay); returns how many."""
