"""`kargah inbox`: the tickets that wait for the owner, oldest first."""
from __future__ import annotations

from datetime import datetime

from kargah.domain.inbox import KINDS, InboxRow, inbox_row, sort_oldest_first
from kargah.ports.tracker import IssueReader


def collect_inbox(tracker: IssueReader, now: datetime) -> list[InboxRow]:
    bot_id, rows = tracker.whoami().id, []
    for label, kind in KINDS.items():
        for ticket in tracker.tickets_with_label(label):
            rows.append(inbox_row(kind, ticket, tracker.comments(ticket.number), bot_id, now))
    return sort_oldest_first(rows)


def format_row(row: InboxRow) -> str:
    hours, rest = divmod(int(row.waiting_seconds), 3600)
    waited = f"{hours}h{rest // 60:02d}m" if hours else f"{rest // 60}m"
    return f"[{row.kind}] #{row.number} {row.title} (waiting {waited}) - {row.summary} - {row.url}"
