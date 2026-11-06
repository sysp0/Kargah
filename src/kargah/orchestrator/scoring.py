"""Grade finished steps with judge agents. Main work always comes first; a limit just means "try next tick"."""
from __future__ import annotations

import itertools
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kargah.domain.agents import AgentSpec, Definition
from kargah.domain.records import StepRecord
from kargah.domain.scoring import ScorerSpec, parse_judgement, sampled, score_of
from kargah.orchestrator.recording import RecordingHarness
from kargah.orchestrator.services import Services
from kargah.ports.harness import HarnessRequest

PROMPT_LIMIT, DIFF_LIMIT = 20_000, 50_000
ASK = "Answer with `LABEL: <value>` and `REASON: <one paragraph>`."
RETRY = f"Your answer did not follow the format. {ASK}"


@dataclass(frozen=True)
class Judged:
    label: str | None             # None: the judge failed or never followed the format
    reason: str
    step_id: str | None           # the judge's own step record


class Scoring:
    def __init__(self, services: Services) -> None:
        self._s = services

    def pending(self, definition: Definition) -> list[tuple[ScorerSpec, StepRecord]]:
        s = self._s
        finished, done = s.scores.finished_runs(), {(r["scorer"], r["step_id"]) for r in s.scores.scores()}
        return [(scorer, step) for step in s.runs.steps() if step.status == "ok" and step.role != "judge"
                and step.run in finished
                for scorer in definition.scorers.values()
                if step.role in scorer.agents and (scorer.name, step.step_id) not in done
                and sampled(step.step_id, scorer.name, scorer.sampling_rate)]

    def score_pending(self, definition: Definition, limit: int = 3) -> int:
        """Grade at most `limit` steps; stops at the first usage limit. Returns how many records were written."""
        written = 0
        for scorer, step in self.pending(definition)[:limit]:
            if not self.score_step(definition, scorer, step):
                break
            written += 1
        return written

    def score_step(self, definition: Definition, scorer: ScorerSpec, step: StepRecord, manual: bool = False) -> bool:
        """False when the judge hit a usage limit (nothing is written, the next tick tries again)."""
        ticket_text = self._s.runs.artifact(step.step_id, "ticket.md") or ""
        judged = self.judge(definition, scorer, self.prompt_for(scorer, step), step.ticket, ticket_text)
        if judged is None:
            return False
        self._s.scores.add(self._record(scorer, step, judged, manual))
        return True

    def judge(self, definition: Definition, scorer: ScorerSpec, prompt: str, ticket: int,
              ticket_text: str) -> Judged | None:
        """Ask the judge (twice at most, if its answer is malformed). None when it hit a usage limit."""
        s = self._s
        agent = AgentSpec("judge", scorer.description, scorer.harness, scorer.model, "read", 10, 0.5, {},
                          scorer.instructions)
        sink: list[StepRecord] = []
        recorder = RecordingHarness(s.harness_for(agent), s.runs, definition.config.prices, s.clock, s.run_id(), ticket,
                                    s.workspace, definition.config.base_branch, ticket_text, itertools.count(1), sink)
        reason = "invalid judge output"
        with tempfile.TemporaryDirectory(prefix="kargah-judge-") as empty:      # the judge never touches the repo
            for attempt in range(2):
                reply = recorder.run(HarnessRequest("judge", prompt, Path(empty), 600, scorer.model))
                if reply.limited:
                    return None
                if not reply.ok:
                    return Judged(None, f"judge failed: {reply.error}", sink[-1].step_id if sink else None)
                if outcome := parse_judgement(reply.text, scorer.labels):
                    return Judged(outcome[0], outcome[1], sink[-1].step_id)
                prompt = f"{prompt}\n\n{RETRY}" if attempt == 0 else prompt
        return Judged(None, reason, sink[-1].step_id if sink else None)

    def prompt_for(self, scorer: ScorerSpec, step: StepRecord) -> str:
        art = lambda name, cap: (self._s.runs.artifact(step.step_id, name) or "")[:cap]      # noqa: E731
        labels = "\n".join(f"- `{x.value}`: {x.description}" for x in scorer.labels)
        diff = art("diff.patch", DIFF_LIMIT)
        parts = [scorer.instructions, f"## Labels\n{labels}", f"## Ticket\n{art('ticket.md', PROMPT_LIMIT)}",
                 f"## Prompt the agent received\n{art('prompt.md', PROMPT_LIMIT)}",
                 f"## The agent's reply\n{art('reply.md', PROMPT_LIMIT)}"]
        if diff:
            parts.append(f"## Diff\n{diff}")
        return "\n\n".join(parts + [ASK])

    def _record(self, scorer: ScorerSpec, step: StepRecord, judged: Judged, manual: bool) -> dict:
        score = score_of(scorer, judged.label) if judged.label else None
        return {"scorer": scorer.name, "step_id": step.step_id, "run": step.run, "ticket": step.ticket,
                "role": step.role, "label": judged.label, "score": score,
                "passed": score is not None and score >= scorer.passing_score, "reason": judged.reason,
                "judge_step": judged.step_id, "at": self._s.clock().isoformat(), "manual": manual}
