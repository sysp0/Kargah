"""Tickets, comments and the labels that carry a ticket's state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Label(StrEnum):
    READY = "ready"
    IN_PROGRESS = "in-progress"
    NEEDS_INFO = "needs-info"
    NEEDS_HUMAN = "needs-human"
    WAITING_REVIEW = "waiting-review"
    BLOCKED = "blocked"
    NEEDS_APPROVAL = "needs-approval"     # a spec is waiting for the owner's /approve
    INTERRUPT = "interrupt"
    DONE = "done"
    APPROVED = "approved"       # set by the owner: the spec is approved (GitLab swallows a /approve comment)
    BUILDER_CLAUDE = "builder-claude"     # set by the owner: Claude builds this ticket, a Codex limit wait is ignored
    KARGAH_AUTO = "kargah-auto"           # on every issue a cron automation opened
    FACTORY_CHANGE = "factory-change"     # set by the owner: this ticket may change the factory definition


@dataclass(frozen=True)
class Author:
    id: int
    username: str


@dataclass(frozen=True)
class Comment:
    id: int
    author: Author
    body: str
    created_at: datetime


@dataclass(frozen=True)
class Ticket:
    number: int
    title: str
    body: str
    labels: frozenset[str]
    open: bool = True
    url: str = ""


STATUS_LABELS = (Label.READY, Label.IN_PROGRESS, Label.NEEDS_INFO, Label.NEEDS_HUMAN, Label.WAITING_REVIEW,
                 Label.BLOCKED, Label.NEEDS_APPROVAL)      # exactly one of these sits on an active ticket
