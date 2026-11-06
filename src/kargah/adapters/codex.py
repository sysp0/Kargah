"""Codex CLI as the build harness: `codex exec` with the prompt on stdin, writing only inside the working copy."""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from kargah.adapters.env import clean_env
from kargah.adapters.limits import is_limit, resets_at
from kargah.ports.harness import HarnessRequest, HarnessResult


class CodexHarness:
    def __init__(self, binary: str = "codex", now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._bin, self._now = binary, now

    def run(self, request: HarnessRequest) -> HarnessResult:
        with tempfile.TemporaryDirectory(prefix="kargah-codex-") as tmp:
            last = Path(tmp) / "last-message.txt"
            cmd = [self._bin, "exec", "--sandbox", "workspace-write", "--json", "--output-last-message", str(last)]
            if request.model:
                cmd += ["-m", request.model]
            cmd.append("-")
            try:
                proc = subprocess.run(cmd, cwd=request.cwd, input=request.prompt, env=clean_env(), text=True,
                                      capture_output=True, timeout=request.timeout_seconds, check=False)
            except subprocess.TimeoutExpired:
                return HarnessResult(ok=False, error=f"codex timed out after {request.timeout_seconds}s")
            text = last.read_text(encoding="utf-8") if last.is_file() else ""
        tokens_in, tokens_out = _usage(proc.stdout)
        if proc.returncode == 0:
            return HarnessResult(ok=True, text=text, tokens_in=tokens_in, tokens_out=tokens_out)
        said = (proc.stdout + proc.stderr)[-3000:]
        if is_limit(said):
            return HarnessResult(ok=False, limited=True, resets_at=resets_at(said, self._now()), error="usage limit")
        return HarnessResult(ok=False, error=f"codex exit {proc.returncode}: {proc.stderr.strip()[-300:]}")


def _usage(stdout: str) -> tuple[int | None, int | None]:
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            u = event["usage"]
            return u.get("input_tokens"), u.get("output_tokens")
    return None, None
