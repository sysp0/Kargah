"""Read how far a ticket got: from git (the branch) and from the bot's own markers."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.handoff import parse_items
from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import Marker, parse_marker
from kargah.domain.review import Verdict, parse_verdict
from kargah.domain.stages import Progress, Review, SpecView
from kargah.domain.ticket import Comment, Label
from kargah.domain.triage import TriageReport, parse_triage
from kargah.ports.workspace import Workspace

APPROVE = "/approve"


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


def read_progress(ws: Workspace, comments: Sequence[Comment], bot_id: int, base: str,
                  labels: frozenset[str] = frozenset()) -> Progress:
    markers = bot_markers(comments, bot_id)
    feedback_at = max((i for i, (_, m) in enumerate(markers) if m.kind == "feedback"), default=-1)
    review_at = [i for i, (_, m) in enumerate(markers) if m.kind == "review" and "sha" in m.attrs]
    reviews = tuple(Review(markers[i][1].attrs["sha"], int(markers[i][1].attrs.get("must_fix", "0")))
                    for i in review_at)
    since = tuple(r for r, i in zip(reviews, review_at, strict=True) if i > feedback_at) if feedback_at >= 0 else None
    return Progress(
        ws.has_work(base), ws.head(), ws.head_state() == "complete", reviews,
        markers[feedback_at][1].attrs.get("sha") if feedback_at >= 0 else None, feedback_at >= 0 and not since, since,
        _triage(markers), _spec(comments, markers, bot_id, Label.APPROVED in labels),
        any(task in ("build", "rework") for _, task, _ in ws.task_commits(base)),
        *_escalations(markers, feedback_at))


def _escalations(markers: list[tuple[Comment, Marker]], feedback_at: int) -> tuple[bool, int]:
    """(Claude was called in since the last change request, how many times in all)."""
    at = [i for i, (_, m) in enumerate(markers) if m.kind == "escalated"]
    return bool(at) and at[-1] > feedback_at, len(at)


def _triage(markers: list[tuple[Comment, Marker]]) -> TriageReport | None:
    for c, m in reversed(markers):
        if m.kind == "triage":
            return parse_triage(c.body)
    return None


def _spec(comments: Sequence[Comment], markers: list[tuple[Comment, Marker]], bot_id: int,
          label: bool = False) -> SpecView | None:
    for c, m in reversed(markers):
        if m.kind == "spec":
            owner = [x for x in sorted(comments, key=lambda x: (x.created_at, x.id))
                     if not is_bot_comment(x, bot_id) and (x.created_at, x.id) > (c.created_at, c.id)]
            approved = label or (bool(owner) and owner[-1].body.strip().startswith(APPROVE))      # the label wins
            return SpecView(m.attrs.get("sha", ""), approved, bool(owner) and not approved)
    return None


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
