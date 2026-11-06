"""What the factory needs from a ticket tracker, split by who uses it (reading vs writing)."""
from __future__ import annotations

from typing import Protocol

from kargah.domain.ticket import Author, Comment, Ticket


class IssueReader(Protocol):
    def whoami(self) -> Author:
        """The identity the tracker sees for this adapter's credentials (the bot)."""

    def tickets_with_label(self, label: str, include_closed: bool = False) -> list[Ticket]: ...

    def get_ticket(self, number: int) -> Ticket: ...

    def comments(self, number: int) -> list[Comment]:
        """Human and bot comments, oldest first; system notes excluded."""


class IssueWriter(Protocol):
    def post_comment(self, number: int, body: str) -> Comment: ...

    def add_label(self, number: int, label: str) -> None: ...

    def remove_label(self, number: int, label: str) -> None: ...

    def close_ticket(self, number: int) -> None: ...

    def create_ticket(self, title: str, body: str, labels: tuple[str, ...]) -> int:
        """A new open issue with exactly these labels; returns its number."""


class Tracker(IssueReader, IssueWriter, Protocol):
    """Reader and writer together."""
