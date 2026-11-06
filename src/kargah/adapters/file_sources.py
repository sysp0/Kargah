"""FileSource implementations: a folder on disk (for `kargah validate`) and the remote default branch."""
from __future__ import annotations

from pathlib import Path

from kargah.ports.workspace import Workspace


class DirSource:
    def __init__(self, root: Path) -> None:
        self._root = root

    def read(self, relpath: str) -> str | None:
        path = self._root / relpath
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def list(self, dirpath: str) -> list[str]:
        base = self._root / dirpath
        return sorted(p.relative_to(self._root).as_posix() for p in base.rglob("*") if p.is_file())


class DefaultBranchSource:
    """What the factory trusts: the default branch, never a ticket branch an agent can edit."""

    def __init__(self, workspace: Workspace) -> None:
        self._ws = workspace

    def read(self, relpath: str) -> str | None:
        return self._ws.read_default(relpath)

    def list(self, dirpath: str) -> list[str]:
        return self._ws.list_default(dirpath)
