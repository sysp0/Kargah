"""Acceptance outside the Codex sandbox: run the configured check for every changed test file.

devchain.toml:
  [accept] env_file, setup (run once when a check needs it), no_test_ok (regex of paths that need no test)
  [accept.env] extra environment, ${VAR} expands from the env file and the process
  [[accept.checks]] match (regex on the changed path), run (command; {path} = repo-relative, {abs} = absolute),
                    setup = true when the check needs the setup command first
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import agents, gitops
from .config import Config
from .events import Run


@dataclass
class Outcome:
    ok: bool
    summary: str
    tail: str


def _env_file(path: Path) -> dict:
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip().removeprefix("export ").strip()] = value.strip().strip('"').strip("'")
    return out


def environment(cfg: Config) -> dict:
    base = {}
    env_file = cfg.get("accept.env_file")
    if env_file:
        base.update(_env_file(cfg.root / env_file))
    scope = {**os.environ, **base}
    extra = {k: re.sub(r"\$\{(\w+)\}", lambda m: scope.get(m.group(1), ""), str(v))
             for k, v in (cfg.get("accept.env") or {}).items()}
    return {**base, **extra}


def run(cfg: Config, run_: Run, pkg: str, logdir: Path, tag: str) -> Outcome:
    paths = gitops.changed(cfg.root)
    checks = cfg.get("accept.checks") or []
    plan = []
    for path in paths:
        if not (cfg.root / path).exists():  # a deleted test file has nothing to run
            continue
        for check in checks:
            if re.search(check["match"], path):
                plan.append((path, check))
                break
    if not plan:
        no_test_ok = cfg.get("accept.no_test_ok")
        if paths and no_test_ok and all(re.search(no_test_ok, p) for p in paths):
            return Outcome(True, "no test needed (UI or docs only)", "")
        return Outcome(False, "no changed test file found", "A package that changes code must add or change a test.")
    env = environment(cfg)
    if any(check.get("setup") for _, check in plan) and cfg.get("accept.setup"):
        res = agents.shell(cfg, run_, pkg, "accept", cfg.get("accept.setup"), logdir / f"setup-{tag}.log", env=env)
        if not res.ok:
            tail = "\n".join(line for line in res.text.splitlines()
                             if not re.match(r"^(init-|ALTER|GRANT|REVOKE)", line))[-4000:]
            return Outcome(False, "test setup (migrations) failed", tail)
    passed, failed = [], []
    for i, (path, check) in enumerate(plan):  # every check runs, so one Codex round sees every failing file
        command = check["run"].format(path=path, abs=str(cfg.root / path))
        res = agents.shell(cfg, run_, pkg, "accept", command, logdir / f"check-{tag}-{i}.log", env=env)
        if res.ok:
            passed.append(res.text.splitlines()[-1] if res.text else "ok")
        else:
            failed.append((path, res.text[-3000:]))
    if failed:
        size = max(800, 12000 // len(failed))  # every failing file keeps its share; the first ones are not cut off
        tail = "\n\n".join(f"== {path}\n{text[-size:]}" for path, text in failed)
        return Outcome(False, "check failed: " + ", ".join(path for path, _ in failed)[:300], tail)
    return Outcome(True, "; ".join(passed)[-300:], "")
