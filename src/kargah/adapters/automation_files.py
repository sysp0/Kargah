"""Read `.kargah/automations/<name>/automation.md`; mistakes come back as problems."""
from __future__ import annotations

from kargah.adapters.frontmatter import split_frontmatter
from kargah.domain.automation import Automation
from kargah.domain.cron import validate
from kargah.domain.ticket import STATUS_LABELS
from kargah.errors import KargahError
from kargah.ports.files import FileSource

AUTOMATIONS_DIR = ".kargah/automations"
_KEYS = {"enabled", "cron", "title", "labels"}


def load_automations(source: FileSource, problems: list[str]) -> dict[str, Automation]:
    found: dict[str, Automation] = {}
    for path in source.list(AUTOMATIONS_DIR):
        parts = path.removeprefix(AUTOMATIONS_DIR + "/").split("/")
        if len(parts) != 2 or parts[1] != "automation.md":
            continue
        spec = _parse(parts[0], path, source.read(path) or "", problems)
        if spec is not None:
            found[parts[0]] = spec
    return found


def _parse(name: str, path: str, text: str, problems: list[str]) -> Automation | None:
    try:
        front, body = split_frontmatter(text)
    except KargahError as exc:
        problems.append(f"{path}: {exc}")
        return None
    before = len(problems)
    problems += [f"{path}: unknown key '{k}'" for k in front if k not in _KEYS]
    labels = front.get("labels", [])
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        problems.append(f"{path}: labels must be a list of strings")
        labels = []
    if bad := [x for x in labels if x in {str(s) for s in STATUS_LABELS}]:
        problems.append(f"{path}: labels must not contain the status labels {bad} (the owner activates tickets)")
    if not isinstance(front.get("enabled", False), bool):
        problems.append(f"{path}: enabled must be true or false")
    if problem := validate(str(front.get("cron", ""))):
        problems.append(f"{path}: cron: {problem}")
    if not str(front.get("title", "")).strip() or not body:
        problems.append(f"{path}: needs a title and a body")
    spec = Automation(name, front.get("enabled", False) is True, str(front.get("cron", "")),
                      str(front.get("title", "")), tuple(labels), body)
    return spec if len(problems) == before else None
