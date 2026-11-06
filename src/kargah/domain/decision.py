"""Which tickets the factory may touch, decided only from the tracker (pure)."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kargah.domain.inputs import human_input, is_bot_comment
from kargah.domain.markers import parse_marker
from kargah.domain.ticket import Comment, Label, Ticket


class Action(StrEnum):
    START = "start"
    RESUME = "resume"
    SKIP = "skip"
    BLOCK = "block"
    COMPLETE = "complete"      # the MR was merged
    CANCEL = "cancel"          # the issue was closed while the MR is still open
    REVISE = "revise"          # the owner asked for changes after the handoff


@dataclass(frozen=True)
class ReviseItem:
    source: str                # "mr" (a diff discussion) | "issue" (a /revise comment)
    ref: str                   # discussion id or comment id
    where: str                 # "path:line" or ""
    text: str


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    items: tuple[ReviseItem, ...] = ()


def decide(ticket: Ticket, comments: Sequence[Comment], bot_id: int, now: datetime, max_starts: int) -> Decision:
    labels = ticket.labels
    if Label.INTERRUPT in labels:
        return Decision(Action.SKIP, "interrupt label set: the owner has not cleared it")
    if Label.READY in labels:
        return Decision(Action.START, "labelled ready")
    if Label.NEEDS_INFO in labels:
        if human_input(comments, bot_id):
            return Decision(Action.RESUME, "the owner answered")
        return Decision(Action.SKIP, "waiting for the owner's answer")
    if Label.NEEDS_APPROVAL in labels:
        if human_input(comments, bot_id):
            return Decision(Action.RESUME, "the owner answered the spec")
        return Decision(Action.SKIP, "waiting for the owner's approval of the spec")
    if Label.IN_PROGRESS in labels or Label.WAITING_REVIEW in labels:
        return _recover(comments, bot_id, now, max_starts)
    return Decision(Action.SKIP, "no actionable label")


def _recover(comments: Sequence[Comment], bot_id: int, now: datetime, max_starts: int) -> Decision:
    markers = [m for c in sorted(comments, key=lambda c: (c.created_at, c.id)) if is_bot_comment(c, bot_id)
               if (m := parse_marker(c.body))]
    if markers and markers[-1].kind == "limit":
        resume_at = markers[-1].attrs.get("resume_at")
        if resume_at and datetime.fromisoformat(resume_at) > now:
            return Decision(Action.SKIP, f"usage limit until {resume_at}")
        return Decision(Action.RESUME, "the usage limit is over")
    last_handoff = max((i for i, m in enumerate(markers) if m.kind == "ready"), default=-1)
    starts = sum(1 for m in markers[last_handoff + 1:] if m.kind == "started")      # a new cycle after each handoff
    if starts >= max_starts:
        return Decision(Action.BLOCK, f"{starts} runs stopped without finishing")
    return Decision(Action.RESUME, "a run stopped without finishing")
