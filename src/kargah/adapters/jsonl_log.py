"""log.jsonl: one JSON object per line, append-only, written by the engine (never by a model)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, record: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
