"""A git working copy for one project. The only place that runs git; the token is passed through the environment."""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kargah.errors import KargahError

STATE_TRAILER = "Kargah-State"
MAX_DIFF_CHARS = 200_000


def _ref(base: str) -> str:
    """A branch name means its remote copy; a full commit id (benchmarks) stands for itself."""
    return base if re.fullmatch(r"[0-9a-f]{40}", base) else f"origin/{base}"


class GitWorkspace:
    def __init__(self, root: Path, remote_url: str, token: str, identity: tuple[str, str]) -> None:
        self.root = root
        self._remote = remote_url
        self._name, self._email = identity
        auth = base64.b64encode(f"oauth2:{token}".encode()).decode()
        self._env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "1",
                     "GIT_CONFIG_KEY_0": "http.extraHeader", "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}",
                     "GIT_AUTHOR_NAME": self._name, "GIT_AUTHOR_EMAIL": self._email,
                     "GIT_COMMITTER_NAME": self._name, "GIT_COMMITTER_EMAIL": self._email}

    def _git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        proc = subprocess.run(["git", *args], cwd=cwd or self.root, env=self._env, capture_output=True, text=True,
                              check=False)
        if check and proc.returncode != 0:
            raise KargahError(f"git {args[0]} failed: {proc.stderr.strip()[-300:]}")
        return proc.stdout.strip()

    def refresh(self) -> None:
        if not (self.root / ".git").is_dir():
            self.root.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", self._remote, str(self.root), cwd=self.root.parent)
        self._git("fetch", "origin", "--prune")

    def prepare(self, branch: str, base: str) -> None:
        self.refresh()
        self._git("reset", "--hard", check=False)
        self._git("clean", "-fd")
        remote = self._git("ls-remote", "--heads", "origin", branch)
        if remote:
            self._git("checkout", "-B", branch, f"origin/{branch}")
        else:
            self._git("checkout", "-B", branch, f"origin/{base}")

    def head(self) -> str:
        return self._git("rev-parse", "HEAD")

    def has_work(self, base: str) -> bool:
        return int(self._git("rev-list", "--count", f"{_ref(base)}..HEAD")) > 0

    def task_commits(self, base: str) -> list[tuple[str, str, str]]:
        fmt = (f"%H%x1f%(trailers:key=Kargah-Task,valueonly,unfold)%x1f"
               f"%(trailers:key={STATE_TRAILER},valueonly,unfold)%x1e")
        out = self._git("log", f"{_ref(base)}..HEAD", f"--format={fmt}", check=False)
        rows = [r.strip("\n") for r in out.split("\x1e") if r.strip()]
        return [(a, b.strip(), c.strip()) for a, b, c in (r.split("\x1f") for r in rows)]

    def head_state(self) -> str | None:
        out = self._git("log", "-1", f"--format=%(trailers:key={STATE_TRAILER},valueonly)", check=False)
        return out.strip() or None

    def changed_files(self, base: str) -> list[str]:
        self._git("add", "-A")
        return self._git("diff", "--cached", "--name-only", _ref(base)).splitlines()

    def base_sha(self, base: str) -> str:
        return self._git("rev-parse", _ref(base))

    def diff(self, base: str) -> str:
        self._git("add", "-A")
        return self._git("diff", "--cached", _ref(base))[:MAX_DIFF_CHARS]

    def read_default(self, relpath: str) -> str | None:
        if not self._default_ready():
            return None
        if not self._git("ls-tree", "--name-only", "origin/HEAD", "--", relpath):
            return None
        return self._git("show", f"origin/HEAD:{relpath}")

    def list_default(self, dirpath: str) -> list[str]:
        if not self._default_ready():
            return []
        out = self._git("ls-tree", "-r", "--name-only", "origin/HEAD", "--", dirpath, check=False)
        return sorted(out.splitlines())

    def _default_ready(self) -> bool:
        if not (self.root / ".git").is_dir():
            return False
        if not self._git("rev-parse", "--verify", "-q", "origin/HEAD", check=False):
            self._git("remote", "set-head", "origin", "--auto")
        return True

    def write_file(self, relpath: str, content: str) -> None:
        target = self.root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def commit(self, message: str, trailers: dict[str, str], allow_empty: bool = False) -> str | None:
        self._git("add", "-A")
        if not allow_empty and not self._git("status", "--porcelain"):
            return None
        body = message + "\n\n" + "\n".join(f"{k}: {v}" for k, v in trailers.items())
        self._git("commit", "-q", *(["--allow-empty"] if allow_empty else []), "-m", body)
        return self.head()

    def push(self, branch: str) -> None:
        self._git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")

    @contextmanager
    def base_variant(self, base: str, keep_paths: list[str]) -> Iterator[Path]:
        tmp = Path(tempfile.mkdtemp(prefix="kargah-proof-"))
        try:
            self._git("worktree", "add", "-q", "--detach", str(tmp / "wt"), _ref(base))
            for rel in keep_paths:
                src = self.root / rel
                if src.is_file():
                    (tmp / "wt" / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, tmp / "wt" / rel)
            yield tmp / "wt"
        finally:
            self._git("worktree", "remove", "--force", str(tmp / "wt"), check=False)
            shutil.rmtree(tmp, ignore_errors=True)

    @contextmanager
    def worktree(self, sha: str, path: Path) -> Iterator[GitWorkspace]:
        """A detached checkout of a commit, usable as a workspace of its own (benchmark trials); removed afterwards."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-q", "--detach", str(path), sha)
        try:
            yield GitWorkspace(path, self._remote, "", (self._name, self._email)).using(self._env)
        finally:
            self._git("worktree", "remove", "--force", str(path), check=False)

    def using(self, env: dict[str, str]) -> GitWorkspace:
        self._env = env
        return self
