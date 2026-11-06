"""Run a project command (check, proof) without the factory's secrets in its environment."""
from __future__ import annotations

import subprocess
from pathlib import Path

from kargah.adapters.env import clean_env
from kargah.ports.shell import CommandResult

TAIL_LINES = 10


class BashShell:
    def run(self, command: str, cwd: Path, timeout_seconds: int) -> CommandResult:
        try:
            proc = subprocess.run(["bash", "-c", command], cwd=cwd, env=clean_env(), capture_output=True, text=True,
                                  timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            return CommandResult(124, f"timed out after {timeout_seconds}s")
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        return CommandResult(proc.returncode, "\n".join(lines[-TAIL_LINES:]))
