"""ScoreStore on disk: <workdir>/scores.jsonl (append only); finished runs come from <workdir>/log.jsonl."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from kargah.adapters.jsonl_log import JsonlLog, read_jsonl


class FsScoreStore:
    def __init__(self, workdir: Path) -> None:
        self._scores, self._log = workdir / "scores.jsonl", workdir / "log.jsonl"

    def scores(self) -> list[dict[str, Any]]:
        return read_jsonl(self._scores)

    def add(self, record: dict[str, Any]) -> None:
        JsonlLog(self._scores).append(record)

    def claimed(self) -> set[tuple[str, str]]:
        return {(scorer, step) for r in read_jsonl(self._log) if r.get("kind") == "improvement"
                for scorer, step in r.get("score_keys", [])}

    def finished_runs(self) -> set[str]:
        return {r["run"] for r in read_jsonl(self._log) if r.get("kind", "run") == "run" and "run" in r}
