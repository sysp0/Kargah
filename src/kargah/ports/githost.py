"""Merge requests on the git host."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kargah.domain.ticket import Author, Comment


@dataclass(frozen=True)
class MrView:
    iid: int
    url: str
    state: str                     # opened | merged | closed
    created_at: datetime
    merged_at: datetime | None


@dataclass(frozen=True)
class Discussion:
    id: str
    author: Author
    body: str                      # the first note of the thread
    path: str | None
    line: int | None
    created_at: datetime


class GitHost(Protocol):
    def ensure_draft_mr(self, branch: str, base: str, title: str, description: str) -> str:
        """Create the draft MR for the branch when missing; return its URL."""

    def mark_ready(self, branch: str) -> None: ...

    def find_mr(self, branch: str) -> MrView | None:
        """The newest MR of the branch in any state; None when there is none."""

    def open_discussions(self, branch: str) -> list[Discussion]:
        """Resolvable, unresolved threads of the branch's MR whose first note is not by the bot."""

    def resolve_discussion(self, branch: str, discussion_id: str, reply: str) -> None:
        """Answer in the thread and mark it resolved."""

    def mr_notes(self, branch: str) -> list[Comment]:
        """Non-system notes of the MR, oldest first."""

    def commit_authors(self, branch: str) -> list[str]:
        """Author e-mails of the MR's commits."""
