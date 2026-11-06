"""Every issue the factory opens by itself goes through here: it never labels one `ready` (the owner does)."""
from __future__ import annotations

from collections.abc import Sequence

from kargah.domain.ticket import Label
from kargah.errors import KargahError
from kargah.ports.tracker import IssueWriter


def create_factory_issue(tracker: IssueWriter, title: str, body: str, labels: Sequence[str]) -> int:
    if Label.READY in labels:
        raise KargahError("the factory never labels an issue it creates as ready")
    return tracker.create_ticket(title, body, tuple(labels))
