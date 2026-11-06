"""Merge requests on the git host."""
from __future__ import annotations

from typing import Protocol


class GitHost(Protocol):
    def ensure_draft_mr(self, branch: str, base: str, title: str, description: str) -> str:
        """Create the draft MR for the branch when missing; return its URL."""

    def mark_ready(self, branch: str) -> None: ...
