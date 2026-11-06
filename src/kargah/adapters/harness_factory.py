"""Turn an AgentSpec into the harness that runs it: which CLI, and what it may touch."""
from __future__ import annotations

from kargah.adapters.claude import BUILD_TOOLS, READ_ONLY_TOOLS, ClaudeHarness
from kargah.adapters.codex import CodexHarness
from kargah.domain.agents import AgentSpec
from kargah.errors import KargahError
from kargah.ports.harness import Harness


def make_harness(spec: AgentSpec) -> Harness:
    edits = spec.access == "edit"
    if spec.harness == "codex":
        return CodexHarness(sandbox="workspace-write" if edits else "read-only")
    if spec.harness == "claude":
        return ClaudeHarness(max_budget_usd=spec.max_budget_usd, tools=BUILD_TOOLS if edits else READ_ONLY_TOOLS,
                             permission_mode="acceptEdits" if edits else "")
    raise KargahError(f"unknown harness '{spec.harness}'")
