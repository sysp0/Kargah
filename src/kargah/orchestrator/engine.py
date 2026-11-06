"""The engine: under a lock, pick the one ticket that needs work and run it."""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

from kargah.domain.decision import Action, Decision, decide
from kargah.domain.handoff import decide_handoff
from kargah.domain.ticket import Label, Ticket
from kargah.orchestrator.closing import Closer
from kargah.orchestrator.lock import RunLock
from kargah.orchestrator.run import TicketRun
from kargah.orchestrator.services import Services

ORDER = (Label.IN_PROGRESS, Label.WAITING_REVIEW, Label.NEEDS_INFO, Label.NEEDS_APPROVAL, Label.NEEDS_HUMAN,
         Label.READY)   # recover before starting new


class Engine:
    def __init__(self, services: Services, state_dir: Path) -> None:
        self._s = services
        self._lock_path = state_dir / "run.lock"

    def tick(self) -> str:
        """One pass: "busy" (another run holds the lock), "idle", or the outcome of the run."""
        with RunLock(self._lock_path) as lock:
            if not lock.acquired:
                return "busy"
            s = self._s
            s.workspace.refresh()
            definition = s.load_definition(s.workspace)
            if definition.problems:
                return f"config-error: {definition.problems[0]}"      # no ticket is touched
            cfg = definition.config
            s.runs.prune(s.clock() - timedelta(days=cfg.runs_keep_days))
            run, bot_id = TicketRun(s), s.tracker.whoami().id
            revisions = self._settle_handoffs(run, bot_id)
            for ticket, decision in self._candidates(cfg.max_starts, bot_id, revisions):
                if decision.action is Action.BLOCK:
                    run.block(ticket, decision.reason)
                    continue
                return run.process(ticket, decision)
            return "idle"

    def _settle_handoffs(self, run: TicketRun, bot_id: int) -> list[tuple[Ticket, Decision]]:
        """Tickets waiting for the owner: merged -> complete, issue closed -> cancel, MR gone -> block (none of these
        is a run, none needs an agent). Tickets with change requests are returned for a rework run."""
        s, closer, revisions = self._s, Closer(self._s), []
        for ticket in sorted(s.tracker.tickets_with_label(Label.NEEDS_HUMAN, include_closed=True),
                             key=lambda t: t.number):
            branch = f"kargah/{ticket.number}"
            mr = s.githost.find_mr(branch)
            discussions = s.githost.open_discussions(branch) if mr and mr.state == "opened" else []
            decision = decide_handoff(ticket, s.tracker.comments(ticket.number), mr, discussions, bot_id)
            if decision.action is Action.COMPLETE and mr:
                closer.complete(ticket, mr, bot_id)
            elif decision.action is Action.CANCEL:
                closer.cancel(ticket, mr, bot_id)
            elif decision.action is Action.BLOCK:
                run.block(ticket, decision.reason)
            elif decision.action is Action.REVISE and Label.INTERRUPT not in ticket.labels:
                revisions.append((ticket, decision))
        return revisions

    def watch(self, poll_seconds: float, should_stop: Callable[[], bool], report: Callable[[str], None]) -> None:
        while not should_stop():
            try:
                outcome = self.tick()
            except Exception as exc:  # noqa: BLE001 - the loop must survive one bad ticket; the next tick retries
                outcome = f"error: {type(exc).__name__}: {exc}"
            report(outcome)
            if outcome in ("idle", "busy") or outcome.startswith(("error", "config-error")):
                time.sleep(poll_seconds)

    def _candidates(self, max_starts: int, bot_id: int,
                    revisions: list[tuple[Ticket, Decision]]) -> Iterator[tuple[Ticket, Decision]]:
        s, now = self._s, self._s.clock()
        for label in ORDER:
            if label is Label.NEEDS_HUMAN:
                yield from revisions
                continue
            for ticket in sorted(s.tracker.tickets_with_label(label), key=lambda t: t.number):
                decision = decide(ticket, s.tracker.comments(ticket.number), bot_id, now, max_starts)
                if decision.action is not Action.SKIP:
                    yield ticket, decision
