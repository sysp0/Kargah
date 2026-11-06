"""Has the owner set the `interrupt` label? Asked while an agent runs, but at most once per interval."""
from __future__ import annotations

import time
from collections.abc import Callable

from kargah.domain.ticket import Label
from kargah.ports.tracker import IssueReader


class InterruptWatch:
    def __init__(self, tracker: IssueReader, number: int, interval_seconds: float = 30.0,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._tracker, self._number, self._interval, self._now = tracker, number, interval_seconds, monotonic
        self._checked_at: float | None = None
        self._set = False

    def __call__(self) -> bool:
        if self._set:
            return True
        if self._checked_at is None or self._now() - self._checked_at >= self._interval:
            self._checked_at = self._now()
            self._set = Label.INTERRUPT in self._tracker.get_ticket(self._number).labels
        return self._set
