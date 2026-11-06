"""Read .kargah/config.toml from the default branch into a ProjectConfig; missing file or keys mean defaults."""
from __future__ import annotations

import tomllib
from dataclasses import fields

from kargah.domain.agents import SIZES
from kargah.domain.config import ProjectConfig
from kargah.domain.pricing import ModelPrice
from kargah.errors import KargahError
from kargah.ports.files import FileSource

_MAP = {  # config.toml `section.key` -> ProjectConfig field
    "project.base_branch": "base_branch", "check.command": "check_command", "proof.command": "proof_command",
    "proof.test_paths": "proof_test_paths", "proof.exempt_paths": "proof_exempt_paths",
    "self_improvement.enabled": "self_improvement", "self_improvement.failed_threshold": "improvement_failed_threshold",
    "self_improvement.max_age_days": "improvement_max_age_days", "proof.fail_codes": "proof_fail_codes",
    "limits.max_fix_rounds": "max_fix_rounds",
    "limits.max_rework": "max_rework", "limits.max_claude_helps": "max_claude_helps",
    "runs.keep_days": "runs_keep_days", "limits.max_starts": "max_starts",
    "check.timeout_seconds": "check_timeout_seconds", "stages.triage": "triage_policy", "stages.spec": "spec_policy",
    "stages.spec_min_size": "spec_min_size",
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
    values["prices"] = _prices(data.get("pricing", {}))
    config = ProjectConfig(**values)  # type: ignore[arg-type]
    for name in ("triage_policy", "spec_policy"):
        if getattr(config, name) not in ("auto", "always", "never"):
            raise KargahError(f"{CONFIG}: [stages] {name.removesuffix('_policy')} must be auto, always or never")
    if config.spec_min_size not in SIZES:
        raise KargahError(f"{CONFIG}: [stages] spec_min_size must be one of {', '.join(SIZES)}")
    return config


def _prices(table: dict) -> dict[str, ModelPrice]:
    try:
        return {model: ModelPrice(float(p["input"]), float(p["output"]), float(p.get("cached", p["input"])))
                for model, p in table.items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise KargahError(f"{CONFIG}: [pricing.\"<model>\"] needs numeric input and output ({exc})") from exc


def config_problems(text: str | None) -> list[str]:
    """Keys that used to live in config.toml and moved to `.kargah/agents/<role>/agent.md`."""
    try:
        data = tomllib.loads(text or "")
    except tomllib.TOMLDecodeError:
        return []                     # parse_project_config already reports it
    old = (["[models]"] if "models" in data else []) + [
        f"limits.{k}" for k in ("build_timeout_seconds", "review_timeout_seconds") if k in data.get("limits", {})]
    return [f"{k} moved to .kargah/agents/<role>/agent.md" for k in old]
