"""Fixtures for engine tests: a real local git remote, the in-memory tracker, scripted agents."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memory_tracker import HUMAN, MemoryTracker

from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DefaultBranchSource
from kargah.adapters.fs_runstore import FsRunStore
from kargah.adapters.fs_scores import FsScoreStore
from kargah.adapters.git_workspace import GitWorkspace
from kargah.adapters.jsonl_log import JsonlLog
from kargah.adapters.shell import BashShell
from kargah.orchestrator.engine import Engine
from kargah.orchestrator.services import Services
from kargah.domain.ticket import Comment
from kargah.ports.githost import Discussion, MrView
from kargah.ports.harness import HarnessRequest, HarnessResult

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
SEED = {
    "pyproject.toml": '[project]\nname="calc"\nversion="0"\n[tool.pytest.ini_options]\npythonpath=["src"]\ntestpaths=["tests"]\n',
    "src/calc/__init__.py": "from calc.ops import add\n",
    "src/calc/ops.py": "def add(a, b):\n    return a + b\n",
    "tests/test_ops.py": "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    ".kargah/config.toml": f'[check]\ncommand = "{sys.executable} -m pytest -q"\n[proof]\ncommand = "{sys.executable} -m pytest -q"\n'
                        '[stages]\ntriage = "never"\nspec = "never"\n',
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
    """Merge requests in memory; the tests play the owner with merge(), close(), say()."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self.ready: list[str] = []
        self.drafts: list[str] = []
        self.state: dict[str, str] = {}
        self.created: dict[str, datetime] = {}
        self.merged_at: dict[str, datetime] = {}
        self.threads: dict[str, list[Discussion]] = {}
        self.resolved: list[tuple[str, str]] = []           # (thread id, reply)
        self.notes: dict[str, list[Comment]] = {}
        self.authors: dict[str, list[str]] = {}
        self._ids = iter(range(1000, 9999))

    def ensure_draft_mr(self, branch: str, base: str, title: str, description: str) -> str:
        if branch not in self.drafts:
            self.drafts.append(branch)
            self.state[branch], self.created[branch] = "opened", self._clock()
            self.authors[branch] = ["b@b"]
        return f"https://example/mr/{branch}"

    def mark_ready(self, branch: str) -> None:
        self.ready.append(branch)

    def find_mr(self, branch: str) -> MrView | None:
        if branch not in self.state:
            return None
        return MrView(1, f"https://example/mr/{branch}", self.state[branch], self.created[branch],
                      self.merged_at.get(branch))

    def open_discussions(self, branch: str) -> list[Discussion]:
        done = {tid for tid, _ in self.resolved}
        return [d for d in self.threads.get(branch, []) if d.id not in done]

    def resolve_discussion(self, branch: str, discussion_id: str, reply: str) -> None:
        self.resolved.append((discussion_id, reply))

    def mr_notes(self, branch: str) -> list[Comment]:
        return list(self.notes.get(branch, []))

    def commit_authors(self, branch: str) -> list[str]:
        return list(self.authors.get(branch, []))

    # the owner's side
    def merge(self, branch: str) -> None:
        self.state[branch], self.merged_at[branch] = "merged", self._clock()

    def close(self, branch: str) -> None:
        self.state[branch] = "closed"

    def comment_on_diff(self, branch: str, text: str, path: str = "src/calc/ops.py", line: int = 2) -> str:
        thread_id = f"t{next(self._ids)}"
        self.threads.setdefault(branch, []).append(Discussion(thread_id, HUMAN, text, path, line, self._clock()))
        return thread_id

    def say(self, branch: str, text: str) -> None:
        self.notes.setdefault(branch, []).append(Comment(next(self._ids), HUMAN, text, self._clock()))


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
    planner: Scripted
    clock: Clock
    remote: Path
    workdir: Path

    def log(self) -> list[str]:
        path = self.workdir / "log.jsonl"
        return path.read_text().splitlines() if path.exists() else []

    def remote_log(self, branch: str) -> str:
        return git(self.remote, "log", "--format=%s%n%(trailers:only,unfold)", branch)


def make_world(tmp: Path, builder_steps: list, reviewer_steps: list, files: dict[str, str] | None = None,
               planner_steps: list | None = None) -> World:
    remote = make_remote(tmp, files)
    clock = Clock()
    tracker, host = MemoryTracker(), FakeGitHost(clock)
    builder, reviewer, planner = Scripted(builder_steps), Scripted(reviewer_steps), Scripted(planner_steps or [])
    by_role = {"implement": builder, "review": reviewer}
    workdir = tmp / "work"
    counter = iter(range(1, 1000))
    services = Services(
        tracker=tracker, githost=host, workspace=GitWorkspace(workdir / "repo", str(remote), "x", ("bot", "b@b")),
        harness_for=lambda spec: by_role.get(spec.role, planner), shell=BashShell(), log=JsonlLog(workdir / "log.jsonl"), runs=FsRunStore(workdir), scores=FsScoreStore(workdir), bot_email="b@b",
        load_definition=lambda ws: load_definition(DefaultBranchSource(ws)), clock=clock, run_id=lambda: f"r{next(counter)}")
    return World(Engine(services, workdir / "state"), tracker, host, builder, reviewer, planner, clock, remote, workdir)
