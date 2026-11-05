"""Which comments count as input from a human. The loop guard: the bot's own comments never do."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.markers import carries_marker
from kargah.domain.ticket import Comment


def is_bot_comment(comment: Comment, bot_id: int) -> bool:
    """By author id, and by marker as a second guard (a marked comment is never input)."""
    return comment.author.id == bot_id or carries_marker(comment.body)


def human_input(comments: Sequence[Comment], bot_id: int) -> tuple[Comment, ...]:
    """Human comments after the bot's last comment, oldest first. Empty when the bot spoke last."""
    ordered = sorted(comments, key=lambda c: (c.created_at, c.id))
    last_bot = max((i for i, c in enumerate(ordered) if is_bot_comment(c, bot_id)), default=-1)
    return tuple(c for c in ordered[last_bot + 1:] if not is_bot_comment(c, bot_id))
