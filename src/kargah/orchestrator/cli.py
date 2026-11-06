"""Command line: `python -m kargah.orchestrator.cli run --workdir DIR [--once]`."""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from kargah.adapters.factory_files import load_definition, with_overrides
from kargah.adapters.file_sources import DefaultBranchSource, DirSource
from kargah.adapters.fs_runstore import FsRunStore
from kargah.adapters.fs_scores import FsScoreStore
from kargah.adapters.git_workspace import GitWorkspace
from kargah.adapters.gitlab.githost import GitLabHost
from kargah.adapters.gitlab.http import UrllibHttp
from kargah.adapters.gitlab.tracker import GitLabTracker
from kargah.adapters.harness_factory import make_harness
from kargah.adapters.jsonl_log import JsonlLog
from kargah.adapters.shell import BashShell
from kargah.domain.agents import Definition
from kargah.errors import KargahError
from kargah.orchestrator.engine import Engine
from kargah.orchestrator.inbox import collect_inbox, format_row
from kargah.orchestrator.reporting import build_report, format_report
from kargah.orchestrator.scoring import Scoring
from kargah.orchestrator.services import Services

BOT_EMAIL = "kargah-bot@users.noreply"


def _gitlab_env() -> tuple[str, str, str]:
    try:
        return tuple(os.environ[k] for k in ("KARGAH_GITLAB_URL", "KARGAH_GITLAB_PROJECT", "KARGAH_GITLAB_TOKEN"))
    except KeyError as exc:
        raise KargahError(f"set {exc.args[0]} (see docs/architecture-A.fa.md)") from exc


def _gitlab_tracker() -> GitLabTracker:
    url, project, token = _gitlab_env()
    return GitLabTracker(UrllibHttp(url, token), project)


def build_services(workdir: Path, builder: str = "", build_model: str = "") -> Services:
    url, project, token = _gitlab_env()
    http = UrllibHttp(url, token)
    workspace = GitWorkspace(workdir / "repo", f"{url}/{project}.git", token, ("kargah-bot", BOT_EMAIL))
    return Services(
        tracker=GitLabTracker(http, project), githost=GitLabHost(http, project, url), workspace=workspace,
        harness_for=make_harness, shell=BashShell(), log=JsonlLog(workdir / "log.jsonl"), runs=FsRunStore(workdir), scores=FsScoreStore(workdir), bot_email=BOT_EMAIL,
        load_definition=lambda ws: _overridden(load_definition(DefaultBranchSource(ws)), builder, build_model),
        clock=lambda: datetime.now(UTC), run_id=lambda: uuid.uuid4().hex[:8])


def build_engine(workdir: Path, builder: str = "", build_model: str = "") -> Engine:
    return Engine(build_services(workdir, builder, build_model), workdir / "state")


def score_command(args: argparse.Namespace) -> int:
    """Grade one step by hand: the sampling rate is ignored and the record is marked manual."""
    services = build_services(args.workdir)
    services.workspace.refresh()
    definition = services.load_definition(services.workspace)
    step = next((r for r in services.runs.steps() if r.step_id == args.step), None)
    if step is None or step.role == "judge":
        print(f"kargah: no gradable step '{args.step}' (judge steps are never scored)", file=sys.stderr)
        return 2
    chosen = [s for s in definition.scorers.values() if step.role in s.agents and args.scorer in ("", s.name)]
    if not chosen:
        print(f"kargah: no scorer {args.scorer or ''} applies to the role {step.role}".replace("  ", " "), file=sys.stderr)
        return 2
    scoring = Scoring(services)
    for scorer in chosen:
        print(f"{scorer.name}: {'scored' if scoring.score_step(definition, scorer, step, manual=True) else 'limit'}")
    return 0


def _overridden(definition: Definition, builder: str, model: str) -> Definition:
    """--builder / --build-model win over the files (for the day Codex is at its limit)."""
    changes: dict[str, str] = {}
    if builder:
        changes["harness"] = builder
        implement = definition.agents.get("implement")
        if implement and builder != implement.harness:
            changes["model"] = ""            # a model of the other harness would not be understood
    if model:
        changes["model"] = model
        changes["models_by_size"] = {}            # an explicit model beats the size router
    return with_overrides(definition, "implement", **changes) if changes else definition


def validate(repo: Path) -> int:
    problems = load_definition(DirSource(repo)).problems
    print("\n".join(problems) if problems else "ok")
    return 1 if problems else 0


def _show(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    try:
        if args.command == "report":
            data = build_report(args.workdir, args.since, now)
            print(json.dumps(data, indent=2) if args.json else format_report(data))
        else:
            rows = collect_inbox(_gitlab_tracker(), now)
            print(json.dumps([dataclasses.asdict(r) for r in rows], indent=2) if args.json
                  else "\n".join(format_row(r) for r in rows) or "nothing waits for you")
    except KargahError as exc:
        print(f"kargah: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kargah")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the factory")
    run.add_argument("--workdir", type=Path, required=True)
    run.add_argument("--once", action="store_true", help="one pass, then exit")
    run.add_argument("--poll", type=float, default=60.0)
    run.add_argument("--builder", choices=("codex", "claude"), default="",
                     help="override the implement agent's harness")
    run.add_argument("--build-model", default="")
    report = sub.add_parser("report", help="numbers from the local records of a workdir")
    report.add_argument("--workdir", type=Path, required=True)
    report.add_argument("--since", default="7d", help="12h, 7d, 2w or all")
    report.add_argument("--json", action="store_true")
    inbox = sub.add_parser("inbox", help="the tickets that wait for the owner, oldest first")
    inbox.add_argument("--json", action="store_true")
    score = sub.add_parser("score", help="grade one step by hand with a scorer")
    score.add_argument("--workdir", type=Path, required=True)
    score.add_argument("--step", required=True)
    score.add_argument("--scorer", default="")
    check = sub.add_parser("validate", help="check the factory definition (.kargah/) of a repository")
    check.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.repo)
    if args.command == "score":
        return score_command(args)
    if args.command in ("report", "inbox"):
        return _show(args)
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
