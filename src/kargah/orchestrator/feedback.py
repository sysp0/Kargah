"""The owner's change requests after a handoff: recorded as a comment, and answered when the rework is accepted."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.decision import ReviseItem
from kargah.domain.handoff import format_items
from kargah.domain.markers import bot_comment
from kargah.domain.ticket import Comment
from kargah.orchestrator import texts
from kargah.orchestrator.progress import bot_markers, latest_feedback
from kargah.orchestrator.services import Services


def record_feedback(s: Services, number: int, run: str, head: str, items: Sequence[ReviseItem]) -> None:
    """A durable comment: when the run dies after this point, the next run reworks from it instead of re-handing in."""
    threads = ",".join(i.ref for i in items if i.source == "mr") or "-"
    s.tracker.post_comment(number, bot_comment("feedback", run, texts.feedback_body(format_items(items)),
                                               sha=head, discussions=threads))


def resolve_addressed(s: Services, branch: str, comments: Sequence[Comment], bot_id: int, head: str) -> None:
    """Reply in, and resolve, the diff threads the last feedback named; threads already resolved are left alone."""
    _, named = latest_feedback(comments, bot_id)
    for thread in s.githost.open_discussions(branch):
        if thread.id in named:
            s.githost.resolve_discussion(branch, thread.id, f"Addressed in {head[:8]}.")


def already_handed_over(comments: Sequence[Comment], bot_id: int, head: str) -> bool:
    """A `ready` comment for this very commit exists (a run died after posting it)."""
    return any(m.kind == "ready" and m.attrs.get("sha") == head for _, m in bot_markers(comments, bot_id))
