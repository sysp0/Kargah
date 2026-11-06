"""Read-only access to the files of a project's factory definition (.kargah/): from disk or from the default branch."""
from __future__ import annotations

from typing import Protocol


class FileSource(Protocol):
    def read(self, relpath: str) -> str | None:
        """The file's text; None when it does not exist."""

    def list(self, dirpath: str) -> list[str]:
        """Paths (relative to the project root, sorted) of all files under the directory, recursively."""
