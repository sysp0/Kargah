"""Spec task: an agent writes docs/specs/<n>.md; the only file it may change."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from kargah.domain.agents import AgentSpec
from kargah.domain.ticket import Comment, Ticket
from kargah.domain.triage import TriageReport, acceptance_section, parse_questions
from kargah.ports.harness import Harness, HarnessRequest
from kargah.ports.workspace import Workspace
from kargah.tasks.prompting import compose, conversation, render

SPEC_DIR = "docs/specs"


def spec_path(number: int) -> str:
    return f"{SPEC_DIR}/{number}.md"


@dataclass
class SpecResult:
    status: str                       # done | question | limit | failed | interrupted
    path: str = ""
    questions: tuple[str, ...] = ()
    error: str = ""
    resets_at: datetime | None = None


class SpecTask:
    def __init__(self, harness: Harness, agent: AgentSpec) -> None:
        self._harness, self._agent = harness, agent

    def run(self, ws: Workspace, ticket: Ticket, owner_comments: Sequence[Comment], base: str,
            triage: TriageReport | None, should_stop: Callable[[], bool] | None = None) -> SpecResult:
        path = spec_path(ticket.number)
        extra = acceptance_section(triage.acceptance, triage.references) if triage else ""
        prompt = compose(self._agent, render("spec", number=ticket.number, title=ticket.title, body=ticket.body,
                                             triage=extra, conversation=conversation(owner_comments), path=path))
        for attempt in range(2):
            reply = self._harness.run(HarnessRequest("spec", prompt, ws.root, self._agent.timeout_seconds,
                                                     self._agent.model, should_stop))
            if reply.stopped:
                return SpecResult("interrupted")
            if reply.limited:
                return SpecResult("limit", resets_at=reply.resets_at)
            if not reply.ok:
                return SpecResult("failed", error=reply.error)
            if questions := parse_questions(reply.text):
                return SpecResult("question", questions=questions)
            changed = set(ws.changed_files(base))
            if changed == {path}:
                return SpecResult("done", path)
            prompt = (f"{prompt}\n\nYou changed {sorted(changed) or 'no file'}. Change only `{path}` and nothing "
                      f"else, and write it in full." if attempt == 0 else prompt)
        return SpecResult("failed", error=f"the spec agent did not leave exactly `{path}` as the only change")
