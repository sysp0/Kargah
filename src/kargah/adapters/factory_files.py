"""Read the factory definition: built-in agent defaults overlaid by the project's `.kargah/` files.

Agent files use TOML frontmatter between two `+++` lines. SKILL.md keeps the outside standard (`---`, name and
description). Mistakes never raise: they come back as `Definition.problems`, one "<path>: <message>" each."""
from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from kargah.adapters.file_sources import DirSource
from kargah.adapters.toml_config import CONFIG, config_problems, parse_project_config
from kargah.domain.agents import ACCESS, HARNESSES, ROLES, SIZES, AgentSpec, Definition, SkillRef
from kargah.domain.config import ProjectConfig
from kargah.errors import KargahError
from kargah.ports.files import FileSource

AGENTS_DIR, SKILLS_DIR = ".kargah/agents", ".kargah/skills"
DEFAULTS = DirSource(Path(__file__).resolve().parent.parent / "defaults")
_KEYS = {"description", "harness", "model", "access", "timeout_minutes", "max_budget_usd", "models_by_size"}
_FRONT = re.compile(r"\A\+\+\+\r?\n(.*?)^\+\+\+[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S | re.M)
_SKILL_FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """(frontmatter table, body). No `+++` block means no frontmatter. Raises KargahError on bad TOML."""
    found = _FRONT.match(text)
    if not found:
        return {}, text.strip()
    try:
        return tomllib.loads(found[1]), found[2].strip()
    except tomllib.TOMLDecodeError as exc:
        raise KargahError(f"frontmatter is not valid TOML: {exc}") from exc


def load_definition(source: FileSource) -> Definition:
    problems: list[str] = []
    text = source.read(CONFIG)
    try:
        config = parse_project_config(text)
    except KargahError as exc:
        config, problems = ProjectConfig(), [str(exc)]
    problems += [f"{CONFIG}: {p}" for p in config_problems(text)]
    files = source.list(AGENTS_DIR)
    shared = _skills(source, SKILLS_DIR, problems)
    agents = {role: spec for role in ROLES
              if (spec := _agent(role, source, files, shared, problems)) is not None}
    for unknown in sorted({p.split("/")[2] for p in files} - set(ROLES)):
        problems.append(f"{AGENTS_DIR}/{unknown}: unknown role (known: {', '.join(ROLES)})")
    return Definition(config, agents, tuple(problems))


def _agent(role: str, source: FileSource, files: list[str], shared: dict[str, SkillRef],
           problems: list[str]) -> AgentSpec | None:
    path = f"{AGENTS_DIR}/{role}/agent.md"
    default_text = DEFAULTS.read(f"agents/{role}/agent.md")
    own_text = source.read(path)
    if default_text is None:
        if own_text is not None:
            problems.append(f"{path}: the role '{role}' has no built-in agent yet")
        return None
    try:
        front, body = split_frontmatter(default_text)
        own_front, own_body = split_frontmatter(own_text) if own_text is not None else ({}, "")
    except KargahError as exc:
        problems.append(f"{path}: {exc}")
        return None
    problems += [f"{path}: unknown key '{k}'" for k in own_front if k not in _KEYS]
    merged = {**front, **{k: v for k, v in own_front.items() if k in _KEYS}}
    own_skills = _skills(source, f"{AGENTS_DIR}/{role}/skills", problems)
    spec = _spec(role, merged, own_body or body, tuple({**shared, **own_skills}.values()), path, problems)
    return spec


def _spec(role: str, v: Mapping, body: str, skills: tuple[SkillRef, ...], path: str,
          problems: list[str]) -> AgentSpec | None:
    spec = AgentSpec(role, str(v.get("description", "")), str(v.get("harness", "")), str(v.get("model", "")),
                     str(v.get("access", "")), _int(v.get("timeout_minutes")), _num(v.get("max_budget_usd", 0)),
                     dict(v.get("models_by_size", {})), body, skills)
    before = len(problems)
    if spec.harness not in HARNESSES:
        problems.append(f"{path}: harness must be one of {', '.join(HARNESSES)}")
    if spec.access not in ACCESS:
        problems.append(f"{path}: access must be one of {', '.join(ACCESS)}")
    if not 1 <= spec.timeout_minutes <= 240:
        problems.append(f"{path}: timeout_minutes must be between 1 and 240")
    if spec.max_budget_usd < 0:
        problems.append(f"{path}: max_budget_usd must not be negative")
    if bad := [k for k in spec.models_by_size if k not in SIZES]:
        problems.append(f"{path}: models_by_size has unknown sizes {bad} (use {', '.join(SIZES)})")
    return spec if len(problems) == before else None


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _num(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else -1.0


def _skills(source: FileSource, folder: str, problems: list[str]) -> dict[str, SkillRef]:
    found: dict[str, SkillRef] = {}
    for path in source.list(folder):
        parts = path.removeprefix(folder + "/").split("/")
        if len(parts) != 2 or parts[1] != "SKILL.md":
            continue
        head = _SKILL_FRONT.match(source.read(path) or "")
        meta = dict(re.findall(r"^(name|description):\s*(.*?)\s*$", head[1] if head else "", re.M))
        if meta.get("name") != parts[0]:
            problems.append(f"{path}: `name:` must equal the folder name '{parts[0]}'")
        elif not meta.get("description"):
            problems.append(f"{path}: `description:` must not be empty")
        else:
            found[parts[0]] = SkillRef(parts[0], meta["description"], path)
    return found


def with_overrides(definition: Definition, role: str, **changes: object) -> Definition:
    """A copy of the definition with one agent changed (the command line overrides the files)."""
    agents = {**definition.agents}
    if role in agents:
        agents[role] = replace(agents[role], **changes)
    return replace(definition, agents=agents)
