"""Read `.kargah/scorers/<name>/scorer.md` (and the built-in ones); mistakes come back as problems."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from kargah.adapters.file_sources import DirSource
from kargah.adapters.frontmatter import split_frontmatter
from kargah.domain.agents import HARNESSES, ROLES
from kargah.domain.scoring import ScoreLabel, ScorerSpec
from kargah.errors import KargahError
from kargah.ports.files import FileSource

SCORERS_DIR = ".kargah/scorers"
BUILTIN = DirSource(Path(__file__).resolve().parent.parent / "defaults")
_KEYS = {"description", "agents", "harness", "model", "passing_score", "sampling_rate", "self_improvement", "labels"}


def load_scorers(source: FileSource, problems: list[str]) -> dict[str, ScorerSpec]:
    found: dict[str, ScorerSpec] = {}
    for origin, folder, prefix in ((BUILTIN, "scorers", "scorers"), (source, SCORERS_DIR, SCORERS_DIR)):
        for path in origin.list(folder):
            parts = path.removeprefix(prefix + "/").split("/")
            if len(parts) != 2 or parts[1] != "scorer.md":
                continue
            spec = _parse(parts[0], path, origin.read(path) or "", problems)
            if spec is not None:
                found[parts[0]] = spec
    return found


def _parse(name: str, path: str, text: str, problems: list[str]) -> ScorerSpec | None:
    try:
        front, body = split_frontmatter(text)
    except KargahError as exc:
        problems.append(f"{path}: {exc}")
        return None
    before = len(problems)
    problems += [f"{path}: unknown key '{k}'" for k in front if k not in _KEYS]
    labels = _labels(front.get("labels", []), path, problems)
    spec = ScorerSpec(name, str(front.get("description", "")), tuple(front.get("agents", ())),
                      str(front.get("harness", "")), str(front.get("model", "")), _num(front.get("passing_score")),
                      _num(front.get("sampling_rate", 0)), bool(front.get("self_improvement", False)), labels, body)
    _check(spec, path, problems)
    return spec if len(problems) == before else None


def _labels(raw: object, path: str, problems: list[str]) -> tuple[ScoreLabel, ...]:
    items = []
    for row in raw if isinstance(raw, list) else []:
        if isinstance(row, Mapping) and "value" in row and "score" in row:
            items.append(ScoreLabel(str(row["value"]), _num(row["score"]), str(row.get("description", ""))))
        else:
            problems.append(f"{path}: every [[labels]] needs `value` and `score`")
    return tuple(items)


def _num(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else -1.0


def _check(spec: ScorerSpec, path: str, problems: list[str]) -> None:
    values = [label.value for label in spec.labels]
    if not 1 <= len(values) <= 20 or len(set(values)) != len(values):
        problems.append(f"{path}: 1 to 20 labels with unique values are required")
    if any(not 0 <= label.score <= 1 for label in spec.labels):
        problems.append(f"{path}: every label score must be between 0 and 1")
    if not 0 <= spec.passing_score <= 1:
        problems.append(f"{path}: passing_score must be between 0 and 1")
    elif not any(x.score >= spec.passing_score for x in spec.labels) or \
            not any(x.score < spec.passing_score for x in spec.labels):
        problems.append(f"{path}: needs a label at or above passing_score and one below it")
    if not spec.agents or not set(spec.agents) <= set(ROLES):
        problems.append(f"{path}: agents must be a non-empty list of roles ({', '.join(ROLES)})")
    if not 0 <= spec.sampling_rate <= 100:
        problems.append(f"{path}: sampling_rate must be between 0 and 100")
    if spec.harness not in HARNESSES or not spec.description:
        problems.append(f"{path}: needs a description and harness ({', '.join(HARNESSES)})")
