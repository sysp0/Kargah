"""Running the project's own commands (check, proof)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    tail: str                  # the last lines of the output only


class Shell(Protocol):
    def run(self, command: str, cwd: Path, timeout_seconds: int) -> CommandResult: ...
