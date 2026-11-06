"""Where the engine records one fact per run (log.jsonl)."""
from __future__ import annotations

from typing import Any, Protocol


class LogSink(Protocol):
    def append(self, record: dict[str, Any]) -> None: ...
