"""Read how far a ticket got: from git (the branch) and from the bot's own markers."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.handoff import parse_items
from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import Marker, parse_marker
from kargah.domain.review import Verdict, parse_verdict
from kargah.domain.stages import Progress, Review
from kargah.domain.ticket import Comment
from kargah.ports.workspace import Workspace


def bot_markers(comments: Sequence[Comment], bot_id: int) -> list[tuple[Comment, Marker]]:
    """The bot's own marked comments, oldest first."""
    found = []
    for c in sorted(comments, key=lambda c: (c.created_at, c.id)):
        marker = parse_marker(c.body) if is_bot_comment(c, bot_id) else None
        if marker:
            found.append((c, marker))
    return found


def _review_comments(comments: Sequence[Comment], bot_id: int) -> list[tuple[Comment, dict[str, str]]]:
    return [(c, m.attrs) for c, m in bot_markers(comments, bot_id) if m.kind == "review" and "sha" in m.attrs]


def read_progress(ws: Workspace, comments: Sequence[Comment], bot_id: int, base: str) -> Progress:
    markers = bot_markers(comments, bot_id)
    feedback_at = max((i for i, (_, m) in enumerate(markers) if m.kind == "feedback"), default=-1)
    review_at = [i for i, (_, m) in enumerate(markers) if m.kind == "review" and "sha" in m.attrs]
    reviews = tuple(Review(markers[i][1].attrs["sha"], int(markers[i][1].attrs.get("must_fix", "0")))
                    for i in review_at)
    if feedback_at < 0:
        return Progress(ws.has_work(base), ws.head(), ws.head_state() == "complete", reviews)
    since = tuple(r for r, i in zip(reviews, review_at, strict=True) if i > feedback_at)
    return Progress(ws.has_work(base), ws.head(), ws.head_state() == "complete", reviews,
                    markers[feedback_at][1].attrs.get("sha"), not since, since)


def latest_verdict(comments: Sequence[Comment], bot_id: int, sha: str) -> Verdict | None:
    """The newest review of this commit, read back from the bot's own review comment."""
    for c, attrs in reversed(_review_comments(comments, bot_id)):
        if attrs["sha"] == sha and (verdict := parse_verdict(c.body)):
            return verdict
    return None


def latest_feedback(comments: Sequence[Comment], bot_id: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(the owner's requested changes, the ids of the diff threads they came from) of the last feedback comment."""
    for c, m in reversed(bot_markers(comments, bot_id)):
        if m.kind == "feedback":
            ids = m.attrs.get("discussions", "-")
            return parse_items(c.body), (() if ids == "-" else tuple(ids.split(",")))
    return (), ()
