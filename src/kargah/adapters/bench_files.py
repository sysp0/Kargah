"""Read `.kargah/benchmarks/<suite>/suite.toml` and its `tasks/<task>.toml`; mistakes come back as problems."""
from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Mapping

from kargah.domain.agents import HARNESSES, ROLES
from kargah.domain.bench import BenchTask, Configuration, Suite
from kargah.ports.files import FileSource

BENCH_DIR = ".kargah/benchmarks"
_SUITE_KEYS = {"description", "role", "repetitions", "scorers", "configurations"}
_TASK_KEYS = {"title", "body", "success_criteria", "start_sha", "source_step"}


def load_suites(source: FileSource, scorer_names: set[str], problems: list[str]) -> dict[str, Suite]:
    files = source.list(BENCH_DIR)
    found: dict[str, Suite] = {}
    for path in files:
        parts = path.removeprefix(BENCH_DIR + "/").split("/")
        if len(parts) == 2 and parts[1] == "suite.toml":
            suite = _suite(parts[0], source, files, scorer_names, problems)
            if suite is not None:
                found[parts[0]] = suite
    return found


def _toml(path: str, text: str, problems: list[str]) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        problems.append(f"{path}: not valid TOML: {exc}")
        return {}


def _suite(name: str, source: FileSource, files: list[str], scorer_names: set[str],
           problems: list[str]) -> Suite | None:
    path = f"{BENCH_DIR}/{name}/suite.toml"
    text = source.read(path) or ""
    data, before = _toml(path, text, problems), len(problems)
    problems += [f"{path}: unknown key '{k}'" for k in data if k not in _SUITE_KEYS]
    configs = _configurations(data.get("configurations", []), path, problems)
    scorers = tuple(data.get("scorers", ()))
    problems += [f"{path}: scorer '{s}' does not exist" for s in scorers if s not in scorer_names]
    role, reps = str(data.get("role", "implement")), data.get("repetitions", 1)
    if role != "implement" or role not in ROLES:
        problems.append(f"{path}: role must be 'implement' in this version")
    if not isinstance(reps, int) or isinstance(reps, bool) or reps < 1:
        problems.append(f"{path}: repetitions must be 1 or more")
    task_paths = [p for p in files if p.startswith(f"{BENCH_DIR}/{name}/tasks/") and p.endswith(".toml")]
    tasks = tuple(t for p in task_paths if (t := _task(p, source, problems)) is not None)
    if not tasks:
        problems.append(f"{BENCH_DIR}/{name}/tasks: a suite needs at least one task")
    digest = hashlib.sha256("".join((source.read(p) or "") for p in [path, *sorted(task_paths)]).encode()).hexdigest()
    ok = len(problems) == before
    return Suite(name, str(data.get("description", "")), role, reps if isinstance(reps, int) else 1, scorers, configs,
                 tasks, digest) if ok else None


def _configurations(raw: object, path: str, problems: list[str]) -> tuple[Configuration, ...]:
    rows = [r for r in raw if isinstance(r, Mapping)] if isinstance(raw, list) else []
    names = [str(r.get("name", "")) for r in rows]
    if not 1 <= len(rows) <= 6 or len(set(names)) != len(names) or "" in names:
        problems.append(f"{path}: 1 to 6 [[configurations]] with unique names are required")
    for r in rows:
        if r.get("harness") not in HARNESSES:
            problems.append(f"{path}: configuration '{r.get('name', '')}' needs harness {', '.join(HARNESSES)}")
    return tuple(Configuration(str(r.get("name", "")), str(r.get("harness", "")), str(r.get("model", "")))
                 for r in rows)


def _task(path: str, source: FileSource, problems: list[str]) -> BenchTask | None:
    data, before = _toml(path, source.read(path) or "", problems), len(problems)
    problems += [f"{path}: unknown key '{k}'" for k in data if k not in _TASK_KEYS]
    for key in ("title", "body", "success_criteria"):
        if not str(data.get(key, "")).strip():
            problems.append(f"{path}: `{key}` is required")
    if str(data.get("success_criteria", "")).strip() == "TODO":
        problems.append(f"{path}: success_criteria is still TODO")
    if not re.fullmatch(r"[0-9a-f]{40}", str(data.get("start_sha", ""))):
        problems.append(f"{path}: start_sha must be a full 40-character commit id (not a branch or tag)")
    name = path.rsplit("/", 1)[1].removesuffix(".toml")
    if len(problems) != before:
        return None
    return BenchTask(name, str(data["title"]), str(data["body"]), str(data["success_criteria"]),
                     str(data["start_sha"]), str(data.get("source_step", "")))
