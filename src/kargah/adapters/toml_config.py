"""Read .kargah/config.toml of a project into a ProjectConfig; missing file or keys mean defaults."""
from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path

from kargah.domain.config import ProjectConfig
from kargah.errors import KargahError

_MAP = {  # config.toml `section.key` -> ProjectConfig field
    "project.base_branch": "base_branch", "check.command": "check_command", "proof.command": "proof_command",
    "proof.test_paths": "proof_test_paths", "limits.max_fix_rounds": "max_fix_rounds",
    "limits.max_rework": "max_rework", "limits.max_starts": "max_starts",
    "limits.build_timeout_seconds": "build_timeout_seconds", "limits.review_timeout_seconds": "review_timeout_seconds",
    "models.review": "review_model", "models.build": "build_model",
}


def load_project_config(repo_root: Path) -> ProjectConfig:
    path = repo_root / ".kargah" / "config.toml"
    if not path.is_file():
        return ProjectConfig()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise KargahError(f"{path}: {exc}") from exc
    known = {f.name for f in fields(ProjectConfig)}
    values: dict[str, object] = {}
    for dotted, name in _MAP.items():
        section, key = dotted.split(".")
        if key in data.get(section, {}):
            value = data[section][key]
            values[name] = tuple(value) if isinstance(value, list) else value
    assert set(values) <= known
    return ProjectConfig(**values)  # type: ignore[arg-type]
