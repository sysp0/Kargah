"""RunStore on disk: <workdir>/steps.jsonl (append only) and <workdir>/runs/<run>/<step_id>/<artifact>."""
from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from kargah.domain.records import StepRecord

DIR_MODE, FILE_MODE = 0o700, 0o600       # transcripts may contain project data


class FsRunStore:
    def __init__(self, workdir: Path) -> None:
        self._runs, self._index = workdir / "runs", workdir / "steps.jsonl"

    def save_step(self, record: StepRecord, artifacts: Mapping[str, str]) -> None:
        folder = self._folder(record.run, record.step_id)
        folder.mkdir(parents=True, exist_ok=True)
        for directory in (self._runs, folder.parent, folder):
            directory.chmod(DIR_MODE)
        for name, text in artifacts.items():
            self._write(folder / _safe(name), text)
        fd = os.open(self._index, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
        with os.fdopen(fd, "a", encoding="utf-8") as out:
            out.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def steps(self) -> list[StepRecord]:
        if not self._index.is_file():
            return []
        return [StepRecord(**json.loads(line)) for line in self._index.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def artifact(self, step_id: str, name: str) -> str | None:
        path = self._folder(step_id.rsplit("-", 1)[0], step_id) / _safe(name)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def prune(self, older_than: datetime) -> int:
        removed = 0
        for record in self.steps():
            folder = self._folder(record.run, record.step_id)
            if datetime.fromisoformat(record.started) < older_than and folder.is_dir():
                shutil.rmtree(folder)
                removed += 1
                if not any(folder.parent.iterdir()):
                    folder.parent.rmdir()
        return removed

    def _folder(self, run: str, step_id: str) -> Path:
        return self._runs / _safe(run) / _safe(step_id)

    @staticmethod
    def _write(path: Path, text: str) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)


def _safe(name: str) -> str:
    if not name or "/" in name or name in (".", "..") or "\\" in name:
        raise ValueError(f"unsafe name: {name!r}")
    return name
