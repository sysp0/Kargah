"""What to do with a ticket the factory has handed to the owner (label `needs-human`), decided as a pure function."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.decision import Action, Decision, ReviseItem
from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import parse_marker
from kargah.domain.ticket import Comment, Ticket
from kargah.ports.githost import Discussion, MrView

REVISE = "/revise"
ITEM = "ITEM: "


def decide_handoff(ticket: Ticket, comments: Sequence[Comment], mr: MrView | None, discussions: Sequence[Discussion],
                   bot_id: int) -> Decision:
    """The first matching rule wins."""
    if mr is None:
        return Decision(Action.BLOCK, "the merge request no longer exists")
    if mr.state == "merged":
        return Decision(Action.COMPLETE, "the merge request was merged")
    if mr.state == "closed":
        return Decision(Action.BLOCK, "the merge request was closed without merging")
    if not ticket.open:
        return Decision(Action.CANCEL, "the issue was closed")
    if items := revise_items(comments, discussions, bot_id):
        return Decision(Action.REVISE, f"{len(items)} requested change(s)", items)
    return Decision(Action.SKIP, "waiting for the owner's review")


def revise_items(comments: Sequence[Comment], discussions: Sequence[Discussion],
                 bot_id: int) -> tuple[ReviseItem, ...]:
    """Open diff threads, plus `/revise ...` comments written after the last handoff. Plain comments are talk between
    people, never an order."""
    items = [ReviseItem("mr", d.id, f"{d.path}:{d.line}" if d.path else "", d.body.strip()) for d in discussions]
    ordered = sorted(comments, key=lambda c: (c.created_at, c.id))
    last_ready = max((i for i, c in enumerate(ordered) if is_bot_comment(c, bot_id)
                      and (m := parse_marker(c.body)) and m.kind == "ready"), default=-1)
    for c in ordered[last_ready + 1:]:
        body = c.body.strip()
        if not is_bot_comment(c, bot_id) and (body == REVISE or body.startswith(REVISE + " ") or
                                              body.startswith(REVISE + "\n")):
            items.append(ReviseItem("issue", str(c.id), "", body.removeprefix(REVISE).strip()))
    return tuple(i for i in items if i.text)


def format_items(items: Sequence[ReviseItem]) -> str:
    """The body lines of a `feedback` comment: the permanent record of what the owner asked for."""
    return "\n".join(f"{ITEM}{i.where or '-'} | {' '.join(i.text.split())}" for i in items)


def parse_items(body: str) -> tuple[str, ...]:
    found = []
    for line in body.splitlines():
        if line.startswith(ITEM):
            where, _, text = line.removeprefix(ITEM).partition(" | ")
            found.append(text if where == "-" else f"{where}: {text}")
    return tuple(found)
