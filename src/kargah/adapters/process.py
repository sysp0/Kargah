"""Run a command that the factory may have to stop: it polls `should_stop` and enforces a timeout."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

GRACE_SECONDS = 10


@dataclass(frozen=True)
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    stopped: bool = False
    timed_out: bool = False


def run_stoppable(cmd: list[str], cwd: Path, input: str, env: Mapping[str, str], timeout_s: float,
                  should_stop: Callable[[], bool] | None = None, poll_s: float = 15.0) -> ProcResult:
    """Output goes to temp files, so a chatty agent cannot fill a pipe and block. The whole process group is
    stopped (agents start children): SIGTERM, then SIGKILL after GRACE_SECONDS."""
    with tempfile.TemporaryDirectory(prefix="kargah-proc-") as tmp:
        files = {name: Path(tmp) / name for name in ("in", "out", "err")}
        files["in"].write_text(input, encoding="utf-8")
        with files["in"].open() as stdin, files["out"].open("w") as out, files["err"].open("w") as err:
            proc = subprocess.Popen(cmd, cwd=cwd, env=dict(env), stdin=stdin, stdout=out, stderr=err, text=True,
                                    start_new_session=True)
            stopped = timed_out = False
            deadline = time.monotonic() + timeout_s
            while proc.poll() is None:
                if should_stop is not None and should_stop():
                    stopped = True
                elif time.monotonic() >= deadline:
                    timed_out = True
                if stopped or timed_out:
                    _terminate(proc)
                    break
                try:
                    proc.wait(timeout=max(0.0, min(poll_s, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
        return ProcResult(proc.returncode, files["out"].read_text(errors="replace"),
                          files["err"].read_text(errors="replace"), stopped, timed_out)


def _terminate(proc: subprocess.Popen) -> None:
    _signal_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _signal_group(proc, signal.SIGKILL)
        proc.wait()


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass
