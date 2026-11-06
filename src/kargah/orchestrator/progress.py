"""Read how far a ticket got: from git (the branch) and from the bot's own review markers."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import parse_marker
from kargah.domain.review import Verdict, parse_verdict
from kargah.domain.stages import Progress, Review
from kargah.domain.ticket import Comment
from kargah.ports.workspace import Workspace


def _review_comments(comments: Sequence[Comment], bot_id: int) -> list[tuple[Comment, dict[str, str]]]:
    found = []
    for c in sorted(comments, key=lambda c: (c.created_at, c.id)):
        marker = parse_marker(c.body) if is_bot_comment(c, bot_id) else None
        if marker and marker.kind == "review" and "sha" in marker.attrs:
            found.append((c, marker.attrs))
    return found


def read_progress(ws: Workspace, comments: Sequence[Comment], bot_id: int, base: str) -> Progress:
    reviews = tuple(Review(a["sha"], int(a.get("must_fix", "0"))) for _, a in _review_comments(comments, bot_id))
    return Progress(ws.has_work(base), ws.head(), ws.head_state() == "complete", reviews)


def latest_verdict(comments: Sequence[Comment], bot_id: int, sha: str) -> Verdict | None:
    """The newest review of this commit, read back from the bot's own review comment."""
    for c, attrs in reversed(_review_comments(comments, bot_id)):
        if attrs["sha"] == sha and (verdict := parse_verdict(c.body)):
            return verdict
    return None
