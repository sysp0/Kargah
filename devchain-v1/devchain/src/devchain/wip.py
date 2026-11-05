"""Work in progress of a task that stopped (a question, stuck, a wait, a limit, a crash): kept on the server in
.devchain/wip/<plan>/<task>/ as a patch with the Codex session and the commit it was made on, so the tree is clean
for the next task. It never goes on the branch.

Going on: when no commit since then touched the task's files, the patch comes back and the same Codex session goes
on; otherwise the task starts fresh and the progress comment guides Codex (the old session remembers old code).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import gitops


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


class Wip:
    def __init__(self, root: Path, folder: Path):
        self.root, self.folder = root, folder

    def dir(self, task: str) -> Path:
        return self.folder / task

    def load(self, task: str) -> dict | None:
        meta = self.dir(task) / "meta.json"
        return json.loads(meta.read_text(encoding="utf-8")) if meta.is_file() else None

    def tasks(self) -> list[str]:
        return sorted(p.name for p in self.folder.iterdir() if (p / "meta.json").is_file()) \
            if self.folder.is_dir() else []

    def save(self, task: str, session: str = "", reason: str = "") -> list[str]:
        """Keep the tree's changes and the session, then clean the tree. Returns the changed paths."""
        from .feature import _restore

        changed = gitops.changed(self.root)
        d = self.dir(task)
        d.mkdir(parents=True, exist_ok=True)
        patch = ""
        if changed:
            gitops.git(self.root, "add", "-A")
            patch = gitops.git(self.root, "diff", "--cached", "--binary", "HEAD", strip=False)
            gitops.git(self.root, "reset", "-q")
        old = self.load(task) or {}
        meta = {"session": session or old.get("session", ""), "base": gitops.git(self.root, "rev-parse", "HEAD"),
                "files": changed, "reason": reason, "saved": time.time()}
        # the work is on disk (and read back) before the tree is cleaned: a crash now loses nothing
        write_atomic(d / "work.patch", patch)
        write_atomic(d / "meta.json", json.dumps(meta, indent=1))
        if changed and (d / "work.patch").read_text(encoding="utf-8") != patch:
            raise OSError(f"the kept work of {task} did not reach the disk; the tree is left as it is")
        _restore(self.root, changed)
        return changed

    def stale(self, task: str) -> list[str]:
        """The task's files that commits changed since its work was saved (then it starts fresh)."""
        meta = self.load(task) or {}
        if not meta.get("base") or not meta.get("files"):
            return []
        moved = gitops.git(self.root, "diff", "--name-only", meta["base"], "HEAD", check=False).splitlines()
        return sorted(set(moved) & set(meta["files"]))

    def restore(self, task: str) -> bool:
        """Put the kept work back in the (clean) tree. False when it cannot apply; the caller drops it."""
        patch = self.dir(task) / "work.patch"
        if not patch.is_file() or not patch.read_text(encoding="utf-8").strip():
            return True
        for check in (True, False):
            args = ["git", "apply", "--whitespace=nowarn", *(["--check"] if check else []), str(patch)]
            if subprocess.run(args, cwd=self.root, capture_output=True).returncode != 0:
                return False
        return True

    def drop(self, task: str) -> None:
        shutil.rmtree(self.dir(task), ignore_errors=True)
