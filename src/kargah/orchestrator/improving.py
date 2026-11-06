"""Self-improvement: turn repeated failed scores of one agent into one issue for the owner. Never labelled `ready`."""
from __future__ import annotations

from collections import defaultdict

from kargah.domain.agents import Definition
from kargah.domain.improvement import Failure, due, failures, issue_text, open_roles
from kargah.domain.ticket import Label
from kargah.orchestrator.services import Services


class Improving:
    def __init__(self, services: Services) -> None:
        self._s = services

    def propose(self, definition: Definition) -> list[int]:
        """Issue numbers created in this pass (at most one per role)."""
        s, cfg = self._s, definition.config
        own = {name for name, scorer in definition.scorers.items() if scorer.self_improvement}
        if not cfg.self_improvement or not own:
            return []
        by_role: dict[str, list[Failure]] = defaultdict(list)
        for f in failures(s.scores.scores(), own, s.scores.claimed()):
            by_role[f.role].append(f)
        waiting = open_roles(t.body for t in s.tracker.tickets_with_label(Label.FACTORY_CHANGE))
        created = []
        for role, found in sorted(by_role.items()):
            if role in waiting or not due(found, cfg.improvement_failed_threshold, cfg.improvement_max_age_days,
                                          s.clock()):
                continue
            title, body = issue_text(role, found)
            number = s.tracker.create_ticket(title, body, (Label.FACTORY_CHANGE,))     # `ready` is the owner's
            s.log.append({"kind": "improvement", "issue": number, "role": role,
                          "score_keys": [[f.scorer, f.step_id] for f in found]})
            created.append(number)
        return created
