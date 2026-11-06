"""A Harness that records every call as a step (record + prompt, reply, diff, ticket) and passes the result on."""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import datetime

from kargah.domain.pricing import ModelPrice, step_cost
from kargah.domain.records import StepRecord
from kargah.domain.review import parse_question
from kargah.ports.harness import Harness, HarnessRequest, HarnessResult
from kargah.ports.runstore import RunStore
from kargah.ports.workspace import Workspace

ROLE_NAMES = {"build": "implement"}          # HarnessRequest.role -> step role
EDIT_ROLES = ("implement", "spec")           # roles whose steps change files, so a diff is stored


class RecordingHarness:
    def __init__(self, inner: Harness, store: RunStore, prices: Mapping[str, ModelPrice],
                 clock: Callable[[], datetime], run: str, ticket: int, workspace: Workspace, base: str,
                 ticket_text: str, numbers: Iterator[int], sink: list[StepRecord]) -> None:
        self._inner, self._store, self._prices, self._clock = inner, store, prices, clock
        self._run, self._ticket, self._ws, self._base, self._text = run, ticket, workspace, base, ticket_text
        self._numbers, self._sink = numbers, sink
        self.name = inner.name

    def run(self, request: HarnessRequest) -> HarnessResult:
        step_id = f"{self._run}-{next(self._numbers):02d}"
        started, head, base_sha = self._clock(), self._ws.head(), self._ws.base_sha(self._base)
        result = self._inner.run(request)
        role = ROLE_NAMES.get(request.role, request.role)
        cost, source = step_cost(result, request.model, self._prices)
        record = StepRecord(
            step_id, self._run, self._ticket, role, self.name, request.model, started.isoformat(),
            round((self._clock() - started).total_seconds(), 1), _status(result), result.tokens_in, result.tokens_out,
            result.tokens_cached, cost, source, base_sha, head)
        artifacts = {"prompt.md": request.prompt, "reply.md": result.text or result.error, "ticket.md": self._text}
        if role in EDIT_ROLES:
            artifacts["diff.patch"] = self._ws.diff(self._base)
        self._sink.append(record)
        try:
            self._store.save_step(record, artifacts)
        except OSError:
            pass      # shortcut: steps are derived data; a full disk must not undo the agent's work
        return result


def _status(result: HarnessResult) -> str:
    if result.limited:
        return "limit"
    if result.stopped:
        return "stopped"
    if not result.ok:
        return "failed"
    return "question" if parse_question(result.text) else "ok"
