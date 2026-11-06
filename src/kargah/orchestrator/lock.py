"""One run at a time: an exclusive, non-blocking file lock (released by the OS even after a crash)."""
from __future__ import annotations

import fcntl
from pathlib import Path
from types import TracebackType
from typing import IO


class RunLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh: IO[str] | None = None
        self.acquired = False

    def __enter__(self) -> RunLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a+")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except BlockingIOError:
            self._fh.close()
            self._fh = None
        return self

    def __exit__(self, *exc: type[BaseException] | BaseException | TracebackType | None) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
