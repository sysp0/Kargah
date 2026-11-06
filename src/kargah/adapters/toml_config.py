"""Read .kargah/config.toml from the default branch into a ProjectConfig; missing file or keys mean defaults."""
from __future__ import annotations

import tomllib
from dataclasses import fields

from kargah.domain.config import ProjectConfig
from kargah.errors import KargahError
from kargah.ports.files import FileSource

_MAP = {  # config.toml `section.key` -> ProjectConfig field
    "project.base_branch": "base_branch", "check.command": "check_command", "proof.command": "proof_command",
    "proof.test_paths": "proof_test_paths", "proof.fail_codes": "proof_fail_codes",
    "limits.max_fix_rounds": "max_fix_rounds",
    "limits.max_rework": "max_rework", "limits.max_starts": "max_starts",
    "limits.build_timeout_seconds": "build_timeout_seconds", "limits.review_timeout_seconds": "review_timeout_seconds",
    "models.review": "review_model", "models.build": "build_model",
}


CONFIG = ".kargah/config.toml"


def load_project_config(source: FileSource) -> ProjectConfig:
    return parse_project_config(source.read(CONFIG))


def parse_project_config(text: str | None) -> ProjectConfig:
    if text is None:
        return ProjectConfig()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise KargahError(f"{CONFIG}: {exc}") from exc
    known = {f.name for f in fields(ProjectConfig)}
    values: dict[str, object] = {}
    for dotted, name in _MAP.items():
        section, key = dotted.split(".")
        if key in data.get(section, {}):
            value = data[section][key]
            values[name] = tuple(value) if isinstance(value, list) else value
    assert set(values) <= known
    return ProjectConfig(**values)  # type: ignore[arg-type]
