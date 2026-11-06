"""A working copy of the project's repository (git), one ticket branch at a time."""
from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol


class Workspace(Protocol):
    root: Path

    def prepare(self, branch: str, base: str) -> None:
        """Clone or fetch, check out the ticket branch (from origin when it exists, else from base). Clean tree."""

    def head(self) -> str: ...

    def has_work(self, base: str) -> bool:
        """The branch has commits beyond the base."""

    def head_state(self) -> str | None:
        """The `Kargah-State` trailer of HEAD, or None."""

    def changed_files(self, base: str) -> list[str]:
        """Files differing from the base, committed or not (untracked included)."""

    def write_file(self, relpath: str, content: str) -> None: ...

    def commit(self, message: str, trailers: dict[str, str]) -> str | None:
        """Commit everything; None when nothing changed."""

    def push(self, branch: str) -> None: ...

    def base_variant(self, base: str, keep_paths: list[str]) -> AbstractContextManager[Path]:
        """A temporary checkout of the base commit plus the given files from the working tree."""
