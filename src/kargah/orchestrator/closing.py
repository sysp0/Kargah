"""The two endings that need no agent: the owner merged the MR (complete) or closed the issue (cancel)."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import bot_comment
from kargah.domain.ticket import STATUS_LABELS, Comment, Label, Ticket
from kargah.orchestrator import texts
from kargah.orchestrator.progress import bot_markers
from kargah.orchestrator.services import Services
from kargah.ports.githost import MrView


class Closer:
    def __init__(self, services: Services) -> None:
        self._s = services

    def complete(self, ticket: Ticket, mr: MrView, bot_id: int) -> None:
        s, n, run = self._s, ticket.number, self._s.run_id()
        comments = s.tracker.comments(n)
        if not _has(comments, bot_id, "done"):
            s.tracker.post_comment(n, bot_comment("done", run, texts.merged(mr.url)))
        if ticket.open:
            s.tracker.close_ticket(n)
        self._clear(n, add=Label.DONE)            # the commit point: the ticket is never looked at again
        s.log.append(self._record(ticket, comments, mr, bot_id, "merged"))

    def cancel(self, ticket: Ticket, mr: MrView | None, bot_id: int) -> None:
        s, n = self._s, ticket.number
        comments = s.tracker.comments(n)
        if not _has(comments, bot_id, "cancelled"):
            s.tracker.post_comment(n, bot_comment("cancelled", s.run_id(), texts.cancelled()))
        self._clear(n)
        s.log.append(self._record(ticket, comments, mr, bot_id, "cancelled"))

    def _clear(self, number: int, add: Label | None = None) -> None:
        for label in (*STATUS_LABELS, Label.INTERRUPT, Label.APPROVED):
            self._s.tracker.remove_label(number, label)
        if add:
            self._s.tracker.add_label(number, add)

    def _record(self, ticket: Ticket, comments: Sequence[Comment], mr: MrView | None, bot_id: int,
                outcome: str) -> dict:
        s, branch = self._s, f"kargah/{ticket.number}"
        marks = bot_markers(comments, bot_id)
        first = {kind: next((c.created_at for c, m in marks if m.kind == kind), None) for kind in ("started", "ready")}
        notes = [n for n in (s.githost.mr_notes(branch) if mr else []) if not is_bot_comment(n, bot_id)]
        pushers = [e for e in (s.githost.commit_authors(branch) if mr else []) if e != s.bot_email]
        kickoff = first["started"]
        talk = [c for c in comments if not is_bot_comment(c, bot_id) and kickoff and c.created_at > kickoff]
        return {
            "kind": "completion", "schema_version": 1, "ticket": ticket.number, "outcome": outcome,
            "mr_url": mr.url if mr else None, "kickoff_at": _iso(kickoff), "handoff_at": _iso(first["ready"]),
            "first_human_review_at": _iso(min((n.created_at for n in notes), default=None)),
            "merged_at": _iso(mr.merged_at) if mr else None,
            "human_interactions": len(talk) + len(notes) + len(pushers), "human_pushed": bool(pushers),
            "labels": sorted(set(ticket.labels) - {str(x) for x in (*STATUS_LABELS, Label.INTERRUPT, Label.APPROVED)})}


def _has(comments: Sequence[Comment], bot_id: int, kind: str) -> bool:
    return any(m.kind == kind for _, m in bot_markers(comments, bot_id))


def _iso(moment) -> str | None:      # noqa: ANN001 - datetime | None
    return moment.isoformat() if moment else None
