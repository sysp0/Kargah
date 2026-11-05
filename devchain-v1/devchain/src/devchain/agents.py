"""Run Codex, Claude and shell steps as child processes, stream their output into the run log.

Each call writes the raw output to a log file and emits short `live` events for the viewers.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import usage as usage_mod
from .config import Config
from .events import Run

LIMIT_RE = re.compile(r"usage limit|rate limit|session limit|quota|too many requests|try again (in|at)", re.I)
# the model is busy for a moment ("Selected model is at capacity", "529 Overloaded"): a short wait, then resend
BUSY_RE = re.compile(r"at capacity|overloaded|temporarily unavailable|service unavailable", re.I)
WAIT_RE = re.compile(r"try again in ([^\n\"]{1,80})", re.I)
# Claude: "You've hit your session limit · resets 4am (Europe/Berlin)"
RESET_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)\s]+)\))?", re.I)
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]|[\x00-\x08\x0b-\x1f\x7f]")
UNIT = {"d": 86400, "h": 3600, "m": 60, "s": 1}


@dataclass
class Result:
    rc: int
    usage: usage_mod.Usage = field(default_factory=usage_mod.Usage)
    text: str = ""
    log: Path | None = None
    session: str = ""   # Codex thread id: `codex exec resume <id>` goes on with the same context

    @property
    def ok(self) -> bool:
        return self.rc == 0


class Live:
    """Throttled `live` events: at most one line per `every` seconds, plus every forced line."""

    def __init__(self, run: Run, pkg: str | None, step: str, every: float = 0.5):
        self.run, self.pkg, self.step, self.every = run, pkg, step, every
        self.last = 0.0
        self.pending: str | None = None

    def line(self, text: str, force: bool = False) -> None:
        text = " ".join(ANSI_RE.sub("", text).split())[:240]
        if not text:
            return
        t = time.time()
        if force or t - self.last >= self.every:
            self.run.emit("live", pkg=self.pkg, step=self.step, text=text)
            self.last, self.pending = t, None
        else:
            self.pending = text

    def flush(self) -> None:
        if self.pending:
            self.run.emit("live", pkg=self.pkg, step=self.step, text=self.pending)
            self.pending = None


NESTED_ENV = "DEVCHAIN_NESTED"  # set for every agent and shell child; ./dev refuses to start a run under it


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _stream(cmd: list[str], *, cwd: Path, log: Path, stdin_text: str | None = None, env: dict | None = None,
            on_line=None, timeout: float | None = None) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                env={**os.environ, NESTED_ENV: "1", **(env or {})}, errors="replace", start_new_session=True)
        if stdin_text is not None:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        timed_out = threading.Event()

        def kill() -> None:   # a silent command sends no line, so the clock cannot be checked in the read loop
            timed_out.set()
            _kill_group(proc)

        timer = threading.Timer(timeout, kill) if timeout else None
        if timer:
            timer.start()
        try:
            for raw in proc.stdout:
                out.write(raw)
                out.flush()
                if on_line:
                    on_line(raw.rstrip("\n"))
            rc = proc.wait()
        finally:   # ./dev stop in the middle of a step: the step does not outlive the loop
            if timer:
                timer.cancel()
            if proc.poll() is None:
                _kill_group(proc)
        if timed_out.is_set():
            out.write("\ndevchain: step timed out\n")
            return 124
        return rc


def shell(cfg: Config, run: Run, pkg: str | None, step: str, command: str, log: Path,
          env: dict | None = None, timeout: float | None = None) -> Result:
    live = Live(run, pkg, step)
    lines: list[str] = []

    def on_line(text: str) -> None:
        lines.append(text)
        del lines[:-40]
        live.line(text)

    rc = _stream(["bash", "-c", command], cwd=cfg.root, log=log, env=env, on_line=on_line, timeout=timeout)
    live.flush()
    return Result(rc=rc, text="\n".join(lines[-20:]), log=log)


def _reset_seconds(text: str, now: datetime | None = None) -> int | None:
    """Seconds until the clock time of "resets 4am (Europe/Berlin)", the next time it comes."""
    found = RESET_RE.findall(text)
    if not found:
        return None
    hour, minute, half, zone = found[-1]
    hour = int(hour) % 12 + (12 if half.lower() == "pm" else 0) if half else int(hour)
    try:
        tz = ZoneInfo(zone) if zone else None
    except (ZoneInfoNotFoundError, ValueError):
        tz = None
    now = now.astimezone(tz) if now else datetime.now(tz)
    at = now.replace(hour=hour % 24, minute=int(minute or 0), second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=1)
    return int((at - now).total_seconds())


def _limit_seconds(text: str) -> int | None:
    found = WAIT_RE.findall(text)
    if not found:
        return _reset_seconds(text)
    parts = re.findall(r"(\d+)\s*(day|d|hour|hr|h|minute|min|m|second|sec|s)", found[-1], re.I)
    total = sum(int(n) * UNIT[u[0].lower()] for n, u in parts)
    return total or None


def _codex_line(live: Live, total: usage_mod.Usage, text: str, holder: dict | None = None) -> None:
    try:
        event = json.loads(text)
    except json.JSONDecodeError:
        live.line(text)
        return
    if not isinstance(event, dict):
        return
    if event.get("type") == "thread.started" and holder is not None and event.get("thread_id"):
        holder["session"] = str(event["thread_id"])
        return
    found = usage_mod.from_codex_event(event)
    if found:
        total.add(found)
        return
    item = event.get("item") if isinstance(event.get("item"), dict) else None
    if event.get("type") == "item.completed" and item:
        kind = item.get("type") or item.get("item_type")
        if kind == "command_execution":
            live.line(f"$ {item.get('command', '')}")
        elif kind in ("agent_message", "assistant_message"):
            live.line(str(item.get("text", "")).splitlines()[0] if item.get("text") else "message", force=True)
        elif kind == "file_change":
            paths = [c.get("path", "") for c in item.get("changes", []) if isinstance(c, dict)]
            live.line("edit " + ", ".join(paths), force=True)
        elif kind == "reasoning":
            live.line("thinking")
    elif event.get("type") == "error":
        live.line(f"error: {event.get('message', '')}", force=True)


def _wait_limit(cfg: Config, run: Run, pkg: str, agent: str, text: str, attempt: int) -> None:
    """Sleep until the usage limit named in text is over, or a while when the model is busy (settings codex.limit_*
    and codex.busy_wait_seconds, used for Claude too)."""
    default_wait = int(cfg.get("codex.limit_wait_seconds", 1800))
    max_wait = int(cfg.get("codex.limit_max_wait_seconds", 21600))
    margin = int(cfg.get("codex.limit_margin_seconds", 60))
    if BUSY_RE.search(text) and not LIMIT_RE.search(text):  # busy, not out of quota: wait longer on each try
        wait = min(int(cfg.get("codex.busy_wait_seconds", 120)) * attempt, max_wait)
    else:
        wait = min((_limit_seconds(text) or default_wait) + margin, max_wait)
    run.emit("limit_wait", pkg=pkg, agent=agent, seconds=wait, until=time.time() + wait, attempt=attempt)
    time.sleep(wait)
    run.emit("limit_done", pkg=pkg, agent=agent)


CONTINUE = "The usage limit is over. Continue the task exactly where you stopped."


def codex(cfg: Config, run: Run, pkg: str, step: str, prompt: str, logdir: Path, session: str = "") -> Result:
    """codex exec with the prompt on stdin; with a session, `codex exec resume <session>` goes on in the same context
    (setting codex.resume_flags: resume takes no --sandbox). While Codex reports a usage limit or a busy model: wait,
    then go on in the same session when one started, else resend."""
    flags = str(cfg.get("codex.flags", "--sandbox workspace-write --json")).split()
    resume_flags = str(cfg.get("codex.resume_flags", '--json -c sandbox_mode="workspace-write"')).split()
    max_tries = int(cfg.get("codex.max_tries", 24))
    logdir.mkdir(parents=True, exist_ok=True)
    last_file = logdir / "last-message.txt"
    total = usage_mod.Usage(calls=1)
    holder = {"session": session}
    for attempt in range(1, max_tries + 1):
        log = logdir / f"codex-{attempt}.log"
        live = Live(run, pkg, step)
        if holder["session"]:
            cmd = [*cfg.codex_bin(), "exec", "resume", *resume_flags, "--output-last-message", str(last_file),
                   holder["session"], "-"]
        else:
            cmd = [*cfg.codex_bin(), "exec", *flags, "--output-last-message", str(last_file), "-"]
        rc = _stream(cmd, cwd=cfg.root, log=log, stdin_text=prompt,
                     on_line=lambda t, live=live: _codex_line(live, total, t, holder))
        live.flush()
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])
        if rc != 0 and (LIMIT_RE.search(tail) or BUSY_RE.search(tail)):
            _wait_limit(cfg, run, pkg, "codex", tail, attempt)
            if holder["session"]:
                prompt = CONTINUE
            continue
        text = last_file.read_text(encoding="utf-8", errors="replace") if last_file.is_file() else ""
        return Result(rc=rc, usage=total, text=text, log=log, session=holder["session"])
    return Result(rc=75, usage=total, text="still at the usage limit", log=logdir / f"codex-{max_tries}.log",
                  session=holder["session"])


def _claude_line(live: Live, holder: dict, text: str) -> None:
    try:
        event = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(event, dict):
        return
    if event.get("type") == "result":
        holder["result"] = event
        return
    if event.get("type") != "assistant":
        return
    for block in (event.get("message") or {}).get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            args = block.get("input") or {}
            detail = args.get("file_path") or args.get("command") or args.get("pattern") or ""
            live.line(f"{block.get('name')} {detail}")
        elif block.get("type") == "text" and block.get("text"):
            live.line(block["text"].strip().splitlines()[0], force=True)


def claude(cfg: Config, run: Run, pkg: str, step: str, prompt: str, model: str, log: Path,
           extra_flags: list[str] | tuple = ()) -> Result:
    """claude -p in stream-json mode: live tool calls, then usage and cost from the result line.

    While Claude reports a usage or session limit (an error result, or no result): wait, then resend."""
    flags = str(cfg.get("claude.flags", "")).split() + list(extra_flags)
    budget = cfg.get("claude.max_budget_usd")
    if budget is not None:
        flags += ["--max-budget-usd", str(budget)]
    cmd = [*cfg.claude_bin(), "-p", prompt, "--model", model, "--output-format", "stream-json", "--verbose", *flags]
    max_tries = int(cfg.get("codex.max_tries", 24))
    for attempt in range(1, max_tries + 1):
        live = Live(run, pkg, step)
        holder: dict = {}
        rc = _stream(cmd, cwd=cfg.root, log=log,
                     on_line=lambda t, live=live, holder=holder: _claude_line(live, holder, t))
        live.flush()
        result = holder.get("result") or {}
        failed = rc != 0 or not result or bool(result.get("is_error"))
        # the result text names the limit; without a result line, only the last lines of the log (never the
        # transcript, which may quote code about rate limits)
        said = str(result.get("result") or "") if result else \
            "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-3:])
        if failed and attempt < max_tries and (LIMIT_RE.search(said) or BUSY_RE.search(said)):
            _wait_limit(cfg, run, pkg, "claude", said, attempt)
            continue
        found = usage_mod.from_claude_result(result) or usage_mod.Usage(calls=1)
        return Result(rc=rc, usage=found, text=str(result.get("result") or ""), log=log)
    return Result(rc=75, text="still at the usage limit", log=log)
