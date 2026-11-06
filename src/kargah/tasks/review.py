"""Review task: a separate agent reads the diff cold and answers in a fixed format."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kargah.domain.config import ProjectConfig
from kargah.domain.review import Verdict, parse_verdict
from kargah.domain.ticket import Ticket
from kargah.ports.harness import Harness, HarnessRequest
from kargah.ports.workspace import Workspace
from kargah.tasks.prompting import render


@dataclass
class ReviewResult:
    status: str                      # "ok" | "limit" | "failed"
    verdict: Verdict | None = None
    text: str = ""
    error: str = ""
    resets_at: datetime | None = None
    cost_usd: float | None = None


class ReviewTask:
    def __init__(self, harness: Harness, config: ProjectConfig) -> None:
        self._harness, self._cfg = harness, config

    def run(self, ws: Workspace, ticket: Ticket, base: str) -> ReviewResult:
        prompt = render("review", number=ticket.number, title=ticket.title, body=ticket.body, base=base)
        reply = self._harness.run(HarnessRequest("review", prompt, ws.root, self._cfg.review_timeout_seconds,
                                                 self._cfg.review_model))
        if reply.limited:
            return ReviewResult("limit", resets_at=reply.resets_at)
        if not reply.ok:
            return ReviewResult("failed", error=reply.error)
        verdict = parse_verdict(reply.text)
        if verdict is None:
            return ReviewResult("failed", error="the reviewer did not follow the verdict format", text=reply.text)
        return ReviewResult("ok", verdict=verdict, text=reply.text, cost_usd=reply.cost_usd)
