"""QA while the loop builds: a finished part is tested in its own worktree, stack, ports and database.

When every task of a part with a `QA: <suite> S1 ...` line is built, a background thread checks the plan branch out
into qa_worktree.dir, starts the stack there (qa_worktree.up, qa_worktree.env), and runs QA (qa.py) with
commit=False. An app failure becomes an issue labelled qa; the loop triages it like any bug. The green specs stay in
the worktree until the loop is between two tasks on a clean tree (collect): then it copies and commits them. One part
is tested at a time, once per plan commit it finished at (.devchain/qa/<plan>.json).
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import traceback
from pathlib import Path

from . import events, forge, gitops
from . import plan as plan_mod
from .config import Config
from .qa import QA
from .plan_tasks import mark
from .trybox import link

DEFAULT_LINKS = ["project-a/.env", "project-ui/ui/node_modules", "qa/node_modules"]


class QaLoop:
    def __init__(self, cfg: Config, stage: str, journal):
        self.cfg, self.stage, self.journal = cfg, stage, journal
        self.enabled = bool(cfg.get("qa_worktree.enabled", True))
        self.where = (cfg.root / str(cfg.get("qa_worktree.dir", f"../{cfg.root.name}-qa"))).resolve()
        self.state_path = cfg.root / ".devchain" / "qa" / f"{stage}.json"
        self.thread: threading.Thread | None = None
        self.ready: list[tuple[str, list[str]]] = []   # (part, green spec files, relative to the worktree)

    def done(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def remember(self, part: str, sha: str) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({**self.done(), part: sha}), encoding="utf-8")

    def due(self, plan: plan_mod.Plan, built: set[str]) -> tuple[str, str, list[str]] | None:
        """(part, suite, scenarios) of the first part that is fully built, has a QA line and was not tested yet."""
        for name in plan.parts:
            rows = plan.in_part(name)
            qa = plan_mod.qa_line(self.cfg.root / plan.folder / name)
            if qa and rows and all(r.id in built for r in rows) and name not in self.done():
                return name, qa[0], qa[1]
        return None

    def start(self, plan: plan_mod.Plan, built: set[str]) -> None:
        if not self.enabled or (self.thread and self.thread.is_alive()):
            return
        found = self.due(plan, built)
        if not found:
            return
        part, suite, scenarios = found
        sha = gitops.git(self.cfg.root, "rev-parse", "--short", "HEAD")
        self.remember(part, sha)   # before the run: a crash must not make the loop test it again and again
        self.journal.decision("QA", part, f"tests {suite} {' '.join(scenarios) or '(all scenarios)'} at {sha} "
                                          f"in {self.where}")
        self.thread = threading.Thread(target=self.work, args=(part, suite, scenarios, sha), daemon=True)
        self.thread.start()

    def retest(self, suite: str, sid: str, number: int) -> bool:
        """Test one scenario again after the fix rows of its qa issue were built; False when a run is busy."""
        if not self.enabled or (self.thread and self.thread.is_alive()):
            return False
        sha = gitops.git(self.cfg.root, "rev-parse", "--short", "HEAD")
        self.journal.decision("QA", f"#{number}", f"tests {suite} {sid} again at {sha}")
        self.thread = threading.Thread(target=self.work, args=("", suite, [sid], sha, number), daemon=True)
        self.thread.start()
        return True

    def checkout(self, sha: str) -> None:
        if (self.where / ".git").exists():
            gitops.git(self.where, "reset", "-q", "--hard")
            gitops.git(self.where, "checkout", "-q", "--detach", sha)
        else:
            if self.where.exists() and any(self.where.iterdir()):
                raise RuntimeError(f"{self.where} exists and is not a worktree; set qa_worktree.dir")
            gitops.git(self.cfg.root, "worktree", "prune", check=False)
            gitops.git(self.cfg.root, "worktree", "add", "-q", "--detach", str(self.where), sha)
        for rel in self.cfg.get("qa_worktree.links", DEFAULT_LINKS):
            link(self.cfg.root / rel, self.where / rel)

    def worktree_cfg(self) -> Config:
        data = json.loads(json.dumps(self.cfg.data))   # a copy: the loop's settings stay as they are
        qa = data.setdefault("qa", {})
        for key in ("up", "restart", "reset"):
            if self.cfg.get(f"qa_worktree.{key}"):
                qa[key] = self.cfg.get(f"qa_worktree.{key}")
        return Config(root=self.where, data=data)

    def work(self, part: str, suite: str, scenarios: list[str], sha: str, issue: int | None = None) -> None:
        try:
            self.checkout(sha)
            env = {**os.environ, "DEVCHAIN_ROOT": str(self.cfg.root),
                   **{k: str(v) for k, v in (self.cfg.get("qa_worktree.env") or {}).items()}}
            run = events.create(self.cfg.runs_dir, "qa")
            qa = QA(self.worktree_cfg(), run, suite, scenarios, env=env, commit=False, plan=self.stage, part=part)
            status, text = qa.run_all()
            self.ready.append((part or f"#{issue}", qa.green))
            if issue and status == "done":
                forge.cli(self.cfg).comment(issue, f"{scenarios[0]} passes now at `{sha}`. Close this issue when you "
                                                   "agree.\n\n" + mark("qa-pass", sha=sha))
            self.journal.decision("QA", part, f"{status}: {text} (run {run.id})")
        except Exception as exc:   # QA never stops the loop
            self.journal.error(part, f"QA {type(exc).__name__}: {exc}", traceback.format_exc())

    def collect(self) -> None:
        """Between two tasks, on a clean tree: copy the green specs of finished QA runs and commit them."""
        while self.ready:
            part, specs = self.ready.pop(0)
            copied = []
            for rel in specs:
                src, dst = self.where / rel, self.cfg.root / rel
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    copied.append(rel)
            if copied:
                try:
                    sha = gitops.commit_paths(self.cfg.root, f"qa: specs of {part} pass", *copied)
                except gitops.GitError as exc:
                    from .feature import _restore
                    _restore(self.cfg.root, copied)   # a dirty tree would stop the loop
                    self.journal.decision("QA", part, f"could not commit the green specs: {exc}")
                    continue
                self.journal.decision("QA", part, f"{len(copied)} green specs committed ({sha})")
