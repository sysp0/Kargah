"""Command line: `python -m kargah.orchestrator.cli run --workdir DIR [--once]`."""
from __future__ import annotations

import argparse
import dataclasses
import os
import signal
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from kargah.adapters.claude import BUILD_TOOLS, ClaudeHarness
from kargah.adapters.codex import CodexHarness
from kargah.adapters.file_sources import DefaultBranchSource
from kargah.adapters.fs_runstore import FsRunStore
from kargah.adapters.git_workspace import GitWorkspace
from kargah.adapters.gitlab.githost import GitLabHost
from kargah.adapters.gitlab.http import UrllibHttp
from kargah.adapters.gitlab.tracker import GitLabTracker
from kargah.adapters.jsonl_log import JsonlLog
from kargah.adapters.shell import BashShell
from kargah.adapters.toml_config import load_project_config
from kargah.errors import KargahError
from kargah.orchestrator.engine import Engine
from kargah.orchestrator.services import Services


def build_engine(workdir: Path, builder: str = "codex", build_model: str = "") -> Engine:
    try:
        url, project, token = (os.environ[k] for k in ("KARGAH_GITLAB_URL", "KARGAH_GITLAB_PROJECT", "KARGAH_GITLAB_TOKEN"))
    except KeyError as exc:
        raise KargahError(f"set {exc.args[0]} (see docs/architecture-A.fa.md)") from exc
    http = UrllibHttp(url, token)
    workspace = GitWorkspace(workdir / "repo", f"{url}/{project}.git", token, ("kargah-bot", "kargah-bot@users.noreply"))
    services = Services(
        tracker=GitLabTracker(http, project), githost=GitLabHost(http, project, url), workspace=workspace,
        builder=ClaudeHarness(tools=BUILD_TOOLS, permission_mode="acceptEdits") if builder == "claude" else CodexHarness(),
        reviewer=ClaudeHarness(), shell=BashShell(), log=JsonlLog(workdir / "log.jsonl"), runs=FsRunStore(workdir),
        load_config=lambda ws: _with_model(load_project_config(DefaultBranchSource(ws)), build_model), clock=lambda: datetime.now(UTC), run_id=lambda: uuid.uuid4().hex[:8])
    return Engine(services, workdir / "state")


def _with_model(cfg, model: str):
    return dataclasses.replace(cfg, build_model=model) if model else cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kargah")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the factory")
    run.add_argument("--workdir", type=Path, required=True)
    run.add_argument("--once", action="store_true", help="one pass, then exit")
    run.add_argument("--poll", type=float, default=60.0)
    run.add_argument("--builder", choices=("codex", "claude"), default="codex")
    run.add_argument("--build-model", default="")
    args = parser.parse_args(argv)
    try:
        engine = build_engine(args.workdir, args.builder, args.build_model)
    except KargahError as exc:
        print(f"kargah: {exc}", file=sys.stderr)
        return 2
    if args.once:
        print(engine.tick())
        return 0
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    engine.watch(args.poll, lambda: stop["now"], lambda msg: print(msg, flush=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
