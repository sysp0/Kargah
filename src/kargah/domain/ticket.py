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
    INTERRUPT = "interrupt"
    DONE = "done"
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
                 Label.BLOCKED)      # exactly one of these sits on an active ticket
