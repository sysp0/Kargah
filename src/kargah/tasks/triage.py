"""Triage task: a read-only agent sizes the ticket and writes its acceptance criteria in a fixed format."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from kargah.domain.agents import AgentSpec
from kargah.domain.ticket import Comment, Ticket
from kargah.domain.triage import TriageReport, parse_questions, parse_triage
from kargah.ports.harness import Harness, HarnessRequest
from kargah.ports.workspace import Workspace
from kargah.tasks.prompting import compose, conversation, render

RETRY = ("Your reply did not follow the format. Reply again in exactly the format given: a `SIZE:` line (XS, S, M, L "
         "or XL) and at least one `ACCEPTANCE:` line.")


@dataclass
class TriageResult:
    status: str                       # done | question | limit | failed | interrupted
    report: TriageReport | None = None
    questions: tuple[str, ...] = ()
    error: str = ""
    resets_at: datetime | None = None


class TriageTask:
    def __init__(self, harness: Harness, agent: AgentSpec) -> None:
        self._harness, self._agent = harness, agent

    def run(self, ws: Workspace, ticket: Ticket, owner_comments: Sequence[Comment],
            should_stop: Callable[[], bool] | None = None) -> TriageResult:
        prompt = compose(self._agent, render("triage", number=ticket.number, title=ticket.title, body=ticket.body,
                                             conversation=conversation(owner_comments)))
        for attempt in range(2):
            reply = self._harness.run(HarnessRequest("triage", prompt, ws.root, self._agent.timeout_seconds,
                                                     self._agent.model, should_stop))
            if reply.stopped:
                return TriageResult("interrupted")
            if reply.limited:
                return TriageResult("limit", resets_at=reply.resets_at)
            if not reply.ok:
                return TriageResult("failed", error=reply.error)
            if questions := parse_questions(reply.text):
                return TriageResult("question", questions=questions)
            if report := parse_triage(reply.text):
                return TriageResult("done", report)
            prompt = f"{prompt}\n\n{RETRY}" if attempt == 0 else prompt
        return TriageResult("failed", error="the triage agent did not follow the report format twice")
