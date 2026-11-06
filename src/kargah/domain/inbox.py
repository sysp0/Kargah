"""What waits for the owner: one row per ticket that needs a person (pure)."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import MARKER_PREFIX
from kargah.domain.ticket import Comment, Label, Ticket

KINDS = {Label.NEEDS_INFO: "Question", Label.NEEDS_APPROVAL: "Spec review", Label.NEEDS_HUMAN: "MR review",
         Label.BLOCKED: "Blocked"}
_HEADER = re.compile(r"^\*\*kargah-bot\*\* · .*$")


@dataclass(frozen=True)
class InboxRow:
    kind: str
    number: int
    title: str
    waiting_seconds: float
    summary: str
    url: str


def first_line(body: str) -> str:
    """The first line of what the bot said: no header line, no hidden marker."""
    for line in body.splitlines():
        text = line.strip().lstrip("> ").strip()
        if text and not _HEADER.match(line.strip()) and not text.startswith(MARKER_PREFIX):
            return text
    return ""


def inbox_row(kind: str, ticket: Ticket, comments: Sequence[Comment], bot_id: int, now: datetime) -> InboxRow:
    bot = [c for c in sorted(comments, key=lambda c: (c.created_at, c.id)) if is_bot_comment(c, bot_id)]
    last = bot[-1] if bot else None
    waiting = (now - last.created_at).total_seconds() if last else 0.0
    return InboxRow(kind, ticket.number, ticket.title, waiting, first_line(last.body) if last else "", ticket.url)


def sort_oldest_first(rows: Sequence[InboxRow]) -> list[InboxRow]:
    return sorted(rows, key=lambda r: (-r.waiting_seconds, r.number))
