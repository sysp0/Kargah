"""Run folders and the append-only event log. The runner writes; viewers only read."""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def now() -> float:
    return time.time()


def new_run_id(kind: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{kind}"


@dataclass
class Run:
    dir: Path
    listeners: list = field(default_factory=list, repr=False, compare=False)   # called with every event

    @property
    def id(self) -> str:
        return self.dir.name

    @property
    def events_path(self) -> Path:
        return self.dir / "events.jsonl"

    def pkg_dir(self, pkg: str) -> Path:
        path = self.dir / pkg
        path.mkdir(parents=True, exist_ok=True)
        return path

    def emit(self, type_: str, **fields) -> dict:
        event = {"ts": now(), "type": type_, **fields}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        for listener in self.listeners:
            listener(event)
        return event

    def write_pid(self) -> None:
        (self.dir / "pid").write_text(str(os.getpid()))

    def stop(self) -> None:
        """Ctrl+C for the runner: SIGINT to its process group (Codex and Claude included); it ends as 'stopped'."""
        pid = int((self.dir / "pid").read_text())
        try:
            os.killpg(os.getpgid(pid), signal.SIGINT)
        except (OSError, PermissionError):
            os.kill(pid, signal.SIGINT)

    def alive(self) -> bool:
        try:
            pid = int((self.dir / "pid").read_text())
            os.kill(pid, 0)
        except (OSError, ValueError):
            return False
        return True

    def pid(self) -> int | None:
        try:
            return int((self.dir / "pid").read_text())
        except (OSError, ValueError):
            return None


def create(runs_dir: Path, kind: str) -> Run:
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id(kind)
    path = runs_dir / run_id
    n = 1
    while path.exists():
        n += 1
        path = runs_dir / f"{run_id}-{n}"
    path.mkdir()
    return Run(path)


def open_run(runs_dir: Path, run_id: str | None) -> Run:
    if run_id:
        path = runs_dir / run_id
        if not path.is_dir():
            raise FileNotFoundError(f"no run {run_id} in {runs_dir}")
        return Run(path)
    runs = list_runs(runs_dir)
    if not runs:
        raise FileNotFoundError(f"no runs in {runs_dir}")
    return runs[-1]


def list_runs(runs_dir: Path) -> list[Run]:
    if not runs_dir.is_dir():
        return []
    return [Run(p) for p in sorted(runs_dir.iterdir(), key=lambda p: p.name) if (p / "events.jsonl").is_file()]


def read(path: Path, offset: int = 0) -> tuple[list[dict], int]:
    """Events from byte `offset`, and the new offset. A half-written last line is left for the next read."""
    if not path.is_file():
        return [], offset
    with path.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    out = []
    consumed = 0
    for raw in chunk.splitlines(keepends=True):
        if not raw.endswith(b"\n"):
            break
        consumed += len(raw)
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out, offset + consumed
