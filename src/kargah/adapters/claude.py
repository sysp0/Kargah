"""Claude Code CLI as the review harness: headless `claude -p`, read-only tools plus read-only git."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from kargah.adapters.env import clean_env
from kargah.adapters.limits import is_limit, resets_at
from kargah.adapters.process import run_stoppable
from kargah.ports.harness import HarnessRequest, HarnessResult

READ_ONLY_TOOLS = "Read,Grep,Glob,Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git status:*)"
# Claude as the build harness (the fallback when Codex is at its limit): may edit files and run tests, not push
BUILD_TOOLS = ("Read,Write,Edit,Grep,Glob,Bash(python3:*),Bash(bash scripts/check.sh:*),Bash(scripts/check.sh:*),"
               "Bash(git status:*),Bash(git diff:*),Bash(ls:*)")


class ClaudeHarness:
    name = "claude"

    def __init__(self, binary: str = "claude", max_budget_usd: float = 2.0, tools: str = READ_ONLY_TOOLS,
                 permission_mode: str = "", now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._bin, self._budget, self._now = binary, max_budget_usd, now
        self._tools, self._mode = tools, permission_mode

    def run(self, request: HarnessRequest) -> HarnessResult:
        cmd = [self._bin, "-p", "--output-format", "json", "--allowedTools", self._tools,
               "--max-budget-usd", str(self._budget)]
        if self._mode:
            cmd += ["--permission-mode", self._mode]
        if request.model:
            cmd += ["--model", request.model]
        proc = run_stoppable(cmd, request.cwd, request.prompt, clean_env(["ANTHROPIC_API_KEY"]),
                             request.timeout_seconds, request.should_stop)
        if proc.stopped:
            return HarnessResult(ok=False, stopped=True, error="stopped by the factory")
        if proc.timed_out:
            return HarnessResult(ok=False, error=f"claude timed out after {request.timeout_seconds}s")
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {}
        text = str(result.get("result") or "")
        usage = result.get("usage") or {}
        if proc.returncode == 0 and result and not result.get("is_error"):
            return HarnessResult(ok=True, text=text, cost_usd=result.get("total_cost_usd"),
                                 tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
                                 tokens_cached=usage.get("cache_read_input_tokens"))
        said = text or (proc.stdout + proc.stderr)[-1500:]
        if is_limit(said):
            return HarnessResult(ok=False, limited=True, resets_at=resets_at(said, self._now()), error="usage limit")
        return HarnessResult(ok=False, error=f"claude exit {proc.returncode}: {said[-300:]}")
