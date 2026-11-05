"""Command line: ./dev run | qa | watch | web | runs | resume | stop | log | usage | stats | try."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import traceback

from . import config as config_mod
from . import events as ev
from . import plain
from .agents import NESTED_ENV
from .model import load


def _start(cfg, args, kind: str, stage: str, packages: list[str]) -> ev.Run:
    run = ev.open_run(cfg.runs_dir, args.run_id) if args.run_id else ev.create(cfg.runs_dir, kind)
    run.write_pid()
    run.emit("run_started", kind=kind, stage=stage, packages=packages, argv=sys.argv[1:],
             named=bool(getattr(args, "packages", None)), branch_mode=getattr(args, "branch", None),
             fix=getattr(args, "fix", None))
    return run


def _finish(run: ev.Run, outcome: str, message: str = "") -> int:
    run.emit("run_finished", outcome=outcome, message=message)
    print(f"devchain: run {run.id} {outcome}{': ' + message if message else ''}")
    return 0 if outcome in ("done", "stopped") else 3


def _guarded(run: ev.Run, body) -> int:
    try:
        outcome, message = body()
    except KeyboardInterrupt:
        return _finish(run, "stopped", "interrupted")
    except Exception as exc:  # the run log must say why it ended
        (run.dir / "crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return _finish(run, "failed", f"{type(exc).__name__}: {exc} (see crash.txt)")
    return _finish(run, outcome, message)


def launch(root, run: ev.Run, argv: list[str], session: str) -> str:
    """Start `./dev <argv>` in the background (tmux when present); return where it runs."""
    command = f"cd {shlex.quote(str(root))} && {shlex.quote(str(root / 'dev'))} {shlex.join(argv)}"
    log = run.dir / "runner.log"
    if shutil.which("tmux"):
        subprocess.run(["tmux", "new-session", "-d", "-s", session, f"{command} 2>&1 | tee -a {shlex.quote(str(log))}"],
                       check=True)
        return f"tmux session {session}"
    with log.open("a") as fh:
        subprocess.Popen(["bash", "-c", command], stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    return f"background process, log {log}"


def resume_session(run: ev.Run) -> str:
    return f"dev-{run.id}-resume-{int(time.time())}"


def _detach(cfg, args) -> int:
    """Start the same command in the background (tmux when present), then watch it."""
    kind = args.command
    run = ev.create(cfg.runs_dir, kind)
    argv = [a for a in sys.argv[1:] if a != "--detach"] + ["--run-id", run.id]
    where = launch(cfg.root, run, argv, f"dev-{run.id}")
    print(f"devchain: started run {run.id} in {where}")
    if sys.stdout.isatty():
        return _watch(cfg, run.id, plain_mode=False)
    return 0


def _watch(cfg, run_id: str | None, plain_mode: bool) -> int:
    run = ev.open_run(cfg.runs_dir, run_id)
    if not plain_mode and sys.stdout.isatty():
        try:
            from .tui import run_tui
        except ImportError:
            print("devchain: textual is not installed; showing plain output (uv sync --project devchain)")
        else:
            run_tui(run, cfg.root)
            return 0
    plain.watch(run)
    return 0


def cmd_run(cfg, args) -> int:
    """./dev run <plan>: the loop of one plan (loop.py), in the foreground or detached."""
    from . import plan as plan_mod
    from .loop import Loop, running

    try:
        if plan_mod.read(cfg, args.plan) is None:
            print(f"devchain: no plan folder {plan_mod.folder_of(cfg, args.plan)}", file=sys.stderr)
            return 2
    except ValueError as exc:
        print(f"devchain: {exc}", file=sys.stderr)
        return 2
    other = running(cfg, args.plan)
    if other is not None and not (args.run_id and other.get("run") == args.run_id):
        print(f"devchain: a loop of plan {args.plan} already runs (pid {other.get('pid')}, run {other.get('run')})",
              file=sys.stderr)
        return 2
    if args.detach:
        return _detach(cfg, args)
    run = ev.open_run(cfg.runs_dir, args.run_id) if args.run_id else ev.create(cfg.runs_dir, "loop")
    if not any(e.get("type") == "run_started" for e in ev.read(run.events_path)[0]):
        run.emit("run_started", kind="loop", stage=args.plan, packages=[], argv=sys.argv[1:])
    else:
        run.emit("run_resumed")
    try:
        rc = Loop(cfg, args.plan, run, once=args.once).main()
    except Exception as exc:  # the run log must say why it ended
        (run.dir / "crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return _finish(run, "failed", f"{type(exc).__name__}: {exc} (see crash.txt)")
    if rc == 99:   # devchain changed on disk: the same run goes on in a new process with the new code
        print(f"devchain: devchain changed on disk; run {run.id} goes on with the new code", flush=True)
        os.execv(sys.executable, [sys.executable, "-m", "devchain", "run", args.plan, "--run-id", run.id])
    if rc == 2:
        return 2
    return _finish(run, "stopped" if rc == 0 else "failed", "" if rc == 0 else "see loop.log and the status issue")


def loops(cfg, plan: str | None) -> list[tuple[str, dict]]:
    """(plan, {pid, run}) of every running loop, or of the named plan."""
    from .loop import running

    folder = cfg.root / ".devchain" / "locks"
    names = [plan] if plan else sorted(p.stem for p in folder.glob("*.lock")) if folder.is_dir() else []
    return [(name, info) for name in names if (info := running(cfg, name)) is not None]


def cmd_resume(cfg, args) -> int:
    """Wake a waiting loop at once (it reads the issues again); a loop that is not running is started by ./dev run."""
    found = loops(cfg, args.plan)
    if not found:
        print("devchain: no loop is running; start it with ./dev run <plan> --detach")
        return 1
    for name, info in found:
        os.kill(int(info["pid"]), signal.SIGUSR1)
        print(f"devchain: woke the loop of {name} (pid {info['pid']})")
    return 0


def cmd_stop(cfg, args) -> int:
    found = loops(cfg, args.plan)
    if not found:
        print("devchain: no loop is running")
        return 0
    for name, info in found:
        ev.open_run(cfg.runs_dir, info.get("run")).stop()
        print(f"devchain: stopping the loop of {name}; its task's work is kept, ./dev run goes on with it")
    return 0


def cmd_log(cfg, args) -> int:
    from . import journal

    try:
        plan = args.plan or current_plan(cfg, None)
    except ValueError as exc:
        print(f"devchain: {exc}", file=sys.stderr)
        return 2
    path = cfg.root / ".devchain" / "logs" / f"{plan}.log"
    lines = journal.read(path, item=args.task, role=args.role, errors=args.errors, last=args.n)
    print("\n".join(lines) if lines else f"devchain: no lines in {path}", flush=True)
    seen = len(journal.read(path, item=args.task, role=args.role, errors=args.errors, last=10 ** 9))
    while args.follow:
        time.sleep(2)
        found = journal.read(path, item=args.task, role=args.role, errors=args.errors, last=10 ** 9)
        for line in found[seen:]:
            print(line, flush=True)
        seen = len(found)
    return 0


def cmd_qa(cfg, args) -> int:
    from .qa import QA

    if args.detach:
        return _detach(cfg, args)
    run = _start(cfg, args, "qa", args.suite, args.scenarios)
    qa = QA(cfg, run, args.suite, args.scenarios)
    return _guarded(run, qa.run_all)


def current_plan(cfg, name: str | None) -> str:
    """The plan named on the command line, else the plan of the newest loop run."""
    if name:
        return name
    for run in reversed(ev.list_runs(cfg.runs_dir)):
        view = load(run)
        if view.kind in ("loop", "feature") and view.stage:
            return view.stage
    raise ValueError("no loop run yet; name the plan")


def cmd_try(cfg, args) -> int:
    from . import trybox

    if args.part == "stop":
        return trybox.stop(cfg)
    try:
        return trybox.start(cfg, current_plan(cfg, args.plan), args.part, args.fixed, args.seed)
    except (ValueError, trybox.TryError) as exc:
        print(f"devchain: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dev", description="Development chain: build plan packages, QA, watch runs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="the loop of a plan: builds its tasks, reads its issues, waits for you")
    p.add_argument("plan", help="plan folder docs/devchain-plan/<plan>/")
    p.add_argument("--detach", action="store_true", help="run in the background (tmux) and open the viewer")
    p.add_argument("--once", action="store_true", help="one round, then stop (for a test)")
    p.add_argument("--run-id", help=argparse.SUPPRESS)

    p = sub.add_parser("qa", help="write and run Playwright scenarios; app failures become qa issues")
    p.add_argument("suite", help="scenario file: docs/qa/<suite>.md")
    p.add_argument("scenarios", nargs="*", help="scenario ids (default: all in the suite)")
    p.add_argument("--detach", action="store_true")
    p.add_argument("--run-id", help=argparse.SUPPRESS)

    p = sub.add_parser("watch", help="viewer for a run (default: the latest)")
    p.add_argument("run_id", nargs="?")
    p.add_argument("--plain", action="store_true", help="plain text instead of the TUI")

    p = sub.add_parser("web", help="read-only web viewer of every run (default http://127.0.0.1:8765/)")
    p.add_argument("--host", help="address to listen on (default web.host); 0.0.0.0 opens it to the network")
    p.add_argument("--port", type=int, help="port (default web.port)")

    sub.add_parser("runs", help="list runs")

    p = sub.add_parser("resume", help="wake the waiting loop at once (it reads the issues again)")
    p.add_argument("plan", nargs="?")

    p = sub.add_parser("stop", help="stop the loop (like Ctrl+C); the task's work is kept")
    p.add_argument("plan", nargs="?")

    p = sub.add_parser("log", help="the loop's decisions: picks, holds, answers, calls, errors")
    p.add_argument("plan", nargs="?")
    p.add_argument("--task", help="only one task or issue (P12, #52)")
    p.add_argument("--role", help="only one kind: Pick, Build, Hold, Release, Question, Stuck, Call, Error, Help ...")
    p.add_argument("--errors", action="store_true", help="only errors and help")
    p.add_argument("-n", type=int, default=80, help="last N lines (default 80)")
    p.add_argument("-f", "--follow", action="store_true", help="keep printing new lines")

    p = sub.add_parser("stats", help="time, rounds, failed checks and cost per package and step, from all runs")
    p.add_argument("plan", nargs="?", help="plan name, for the fix rows written later")

    p = sub.add_parser("usage", help="token and cost table of a run")
    p.add_argument("run_id", nargs="?")

    p = sub.add_parser("try", help="start the app of a finished part in its own folder and ports, to test it")
    p.add_argument("part", help="part number or name (02, 02-registry-catalog), or stop")
    p.add_argument("--fixed", action="store_true", help="also take the fixes of the part's issue rows")
    p.add_argument("--seed", help="the QA data set to load (qa.seeds, default the first: shop)")
    p.add_argument("--plan", help="plan folder name (default: the plan of the newest feature run)")

    args = parser.parse_args(argv)
    try:
        cfg = config_mod.load()
    except config_mod.ConfigError as exc:
        print(f"devchain: {exc}", file=sys.stderr)
        return 2
    os.chdir(cfg.root)
    if args.command in ("run", "qa") and os.environ.get(NESTED_ENV):
        print("devchain: refusing to start a run from inside a run (an agent called ./dev)", file=sys.stderr)
        return 2
    try:
        if args.command == "run":
            return cmd_run(cfg, args)
        if args.command == "qa":
            return cmd_qa(cfg, args)
        if args.command == "watch":
            return _watch(cfg, args.run_id, args.plain)
        if args.command == "web":
            from .web import serve

            return serve(cfg, args.host, args.port)
        if args.command == "runs":
            print(plain.runs_table(ev.list_runs(cfg.runs_dir)))
            return 0
        if args.command == "resume":
            return cmd_resume(cfg, args)
        if args.command == "stop":
            return cmd_stop(cfg, args)
        if args.command == "log":
            return cmd_log(cfg, args)
        if args.command == "try":
            return cmd_try(cfg, args)
        if args.command == "stats":
            from . import stats
            print(stats.report(cfg, args.plan or ""))
            return 0
        if args.command == "usage":
            print(plain.usage_table(load(ev.open_run(cfg.runs_dir, args.run_id))))
            return 0
    except FileNotFoundError as exc:
        print(f"devchain: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
