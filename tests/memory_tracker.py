"""In-memory Tracker for tests; behaves like the real ones (system notes are not modelled)."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kargah.domain.ticket import Author, Comment, Ticket

BOT = Author(id=1, username="kargah-bot")
HUMAN = Author(id=2, username="owner")


class MemoryTracker:
    def __init__(self) -> None:
        self._tickets: dict[int, Ticket] = {}
        self._comments: dict[int, list[Comment]] = {}
        self._clock = datetime(2026, 1, 1, tzinfo=UTC)
        self._next_id = 100

    def open_ticket(self, title: str, body: str = "", labels: tuple[str, ...] = ()) -> int:
        number = len(self._tickets) + 1
        self._tickets[number] = Ticket(number, title, body, frozenset(labels), url=f"https://example/issues/{number}")
        self._comments[number] = []
        return number

    def human_says(self, number: int, body: str) -> Comment:
        return self._add(number, HUMAN, body)

    def whoami(self) -> Author:
        return BOT

    def tickets_with_label(self, label: str, include_closed: bool = False) -> list[Ticket]:
        return [t for t in self._tickets.values() if label in t.labels and (t.open or include_closed)]

    def close_ticket(self, number: int) -> None:
        self._tickets[number] = replace(self._tickets[number], open=False)

    def get_ticket(self, number: int) -> Ticket:
        return self._tickets[number]

    def comments(self, number: int) -> list[Comment]:
        return list(self._comments[number])

    def post_comment(self, number: int, body: str) -> Comment:
        return self._add(number, BOT, body)

    def add_label(self, number: int, label: str) -> None:
        t = self._tickets[number]
        self._tickets[number] = replace(t, labels=t.labels | {label})

    def remove_label(self, number: int, label: str) -> None:
        t = self._tickets[number]
        self._tickets[number] = replace(t, labels=t.labels - {label})

    def _add(self, number: int, author: Author, body: str) -> Comment:
        self._clock += timedelta(seconds=1)
        self._next_id += 1
        comment = Comment(self._next_id, author, body, self._clock)
        self._comments[number].append(comment)
        return comment
