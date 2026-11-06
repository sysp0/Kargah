"""Cron automations: open the issue of the newest due slot, once. They never run an agent."""
from __future__ import annotations

from datetime import timedelta

from kargah.domain.agents import Definition
from kargah.domain.automation import issue_text, marker
from kargah.domain.cron import latest_slot
from kargah.domain.ticket import Label
from kargah.orchestrator.factory_issue import create_factory_issue
from kargah.orchestrator.services import Services

LOOKBACK = timedelta(days=7)      # a slot older than this is forgotten, after a long stop only the newest one counts


class Automating:
    def __init__(self, services: Services) -> None:
        self._s = services

    def run(self, definition: Definition) -> list[int]:
        s, now = self._s, self._s.clock()
        due = [(spec, slot) for spec in definition.automations.values() if spec.enabled
               if (slot := latest_slot(spec.cron, now, LOOKBACK))]
        if not due:
            return []
        seen = "\n".join(t.body for t in s.tracker.tickets_with_label(Label.KARGAH_AUTO, include_closed=True))
        created = []
        for spec, slot in due:
            if marker(spec.name, slot) in seen:
                continue
            title, body = issue_text(spec, slot)
            created.append(create_factory_issue(s.tracker, title, body, (Label.KARGAH_AUTO, *spec.labels)))
        return created
