"""Fixtures for engine tests: a real local git remote, the in-memory tracker, scripted agents."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memory_tracker import MemoryTracker

from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DefaultBranchSource
from kargah.adapters.fs_runstore import FsRunStore
from kargah.adapters.git_workspace import GitWorkspace
from kargah.adapters.jsonl_log import JsonlLog
from kargah.adapters.shell import BashShell
from kargah.orchestrator.engine import Engine
from kargah.orchestrator.services import Services
from kargah.ports.harness import HarnessRequest, HarnessResult

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
SEED = {
    "pyproject.toml": '[project]\nname="calc"\nversion="0"\n[tool.pytest.ini_options]\npythonpath=["src"]\ntestpaths=["tests"]\n',
    "src/calc/__init__.py": "from calc.ops import add\n",
    "src/calc/ops.py": "def add(a, b):\n    return a + b\n",
    "tests/test_ops.py": "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    ".kargah/config.toml": f'[check]\ncommand = "{sys.executable} -m pytest -q"\n[proof]\ncommand = "{sys.executable} -m pytest -q"\n',
}
MULTIPLY_TEST = "from calc import multiply\n\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n"
MULTIPLY_CODE = "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n"
EXPORT = "from calc.ops import add, multiply\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env={**GIT_ENV, "PATH": "/usr/bin:/bin"}, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_remote(tmp: Path, files: dict[str, str] | None = None) -> Path:
    remote, seed = tmp / "remote.git", tmp / "seed"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    for rel, text in {**SEED, **(files or {})}.items():
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_text(text)
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", str(remote), "main")
    return remote


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


class FakeGitHost:
    def __init__(self) -> None:
        self.ready: list[str] = []
        self.drafts: list[str] = []

    def ensure_draft_mr(self, branch: str, base: str, title: str, description: str) -> str:
        if branch not in self.drafts:
            self.drafts.append(branch)
        return f"https://example/mr/{branch}"

    def mark_ready(self, branch: str) -> None:
        self.ready.append(branch)


@dataclass
class Scripted:
    """An agent that plays one scripted step per call: step(request) -> HarnessResult."""
    steps: list[Callable[[HarnessRequest], HarnessResult]]
    calls: list[HarnessRequest] = field(default_factory=list)
    name: str = "scripted"

    def run(self, request: HarnessRequest) -> HarnessResult:
        self.calls.append(request)
        return self.steps.pop(0)(request)


def writes(files: dict[str, str], text: str = "done") -> Callable[[HarnessRequest], HarnessResult]:
    def step(request: HarnessRequest) -> HarnessResult:
        for rel, content in files.items():
            (request.cwd / rel).parent.mkdir(parents=True, exist_ok=True)
            (request.cwd / rel).write_text(content)
        return HarnessResult(ok=True, text=text)
    return step


def says(text: str) -> Callable[[HarnessRequest], HarnessResult]:
    return lambda request: HarnessResult(ok=True, text=text)


def multiply_feature() -> Callable[[HarnessRequest], HarnessResult]:
    return writes({"tests/test_multiply.py": MULTIPLY_TEST, "src/calc/ops.py": MULTIPLY_CODE,
                   "src/calc/__init__.py": EXPORT})


@dataclass
class World:
    engine: Engine
    tracker: MemoryTracker
    host: FakeGitHost
    builder: Scripted
    reviewer: Scripted
    clock: Clock
    remote: Path
    workdir: Path

    def log(self) -> list[str]:
        path = self.workdir / "log.jsonl"
        return path.read_text().splitlines() if path.exists() else []

    def remote_log(self, branch: str) -> str:
        return git(self.remote, "log", "--format=%s%n%(trailers:only,unfold)", branch)


def make_world(tmp: Path, builder_steps: list, reviewer_steps: list, files: dict[str, str] | None = None) -> World:
    remote = make_remote(tmp, files)
    tracker, host, clock = MemoryTracker(), FakeGitHost(), Clock()
    builder, reviewer = Scripted(builder_steps), Scripted(reviewer_steps)
    workdir = tmp / "work"
    counter = iter(range(1, 1000))
    services = Services(
        tracker=tracker, githost=host, workspace=GitWorkspace(workdir / "repo", str(remote), "x", ("bot", "b@b")),
        harness_for=lambda spec: builder if spec.role == "implement" else reviewer, shell=BashShell(), log=JsonlLog(workdir / "log.jsonl"), runs=FsRunStore(workdir),
        load_definition=lambda ws: load_definition(DefaultBranchSource(ws)), clock=clock, run_id=lambda: f"r{next(counter)}")
    return World(Engine(services, workdir / "state"), tracker, host, builder, reviewer, clock, remote, workdir)
