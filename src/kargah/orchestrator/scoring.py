"""Grade finished steps with judge agents. Main work always comes first; a limit just means "try next tick"."""
from __future__ import annotations

import itertools
import tempfile
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
        s = self._s
        judge = AgentSpec("judge", scorer.description, scorer.harness, scorer.model, "read", 10, 0.5, {},
                          scorer.instructions)
        sink: list[StepRecord] = []
        recorder = RecordingHarness(s.harness_for(judge), s.runs, definition.config.prices, s.clock, s.run_id(),
                                    step.ticket, s.workspace, definition.config.base_branch,
                                    s.runs.artifact(step.step_id, "ticket.md") or "", itertools.count(1), sink)
        prompt = self._prompt(scorer, step)
        outcome: tuple[str, str] | None = None
        reason = "invalid judge output"
        with tempfile.TemporaryDirectory(prefix="kargah-judge-") as empty:      # the judge never touches the repo
            for attempt in range(2):
                reply = recorder.run(HarnessRequest("judge", prompt, Path(empty), 600, scorer.model))
                if reply.limited:
                    return False
                if not reply.ok:
                    reason = f"judge failed: {reply.error}"
                    break
                if outcome := parse_judgement(reply.text, scorer.labels):
                    break
                prompt = f"{prompt}\n\n{RETRY}" if attempt == 0 else prompt
        s.scores.add(self._record(scorer, step, outcome, reason, sink, manual))
        return True

    def _prompt(self, scorer: ScorerSpec, step: StepRecord) -> str:
        art = lambda name, cap: (self._s.runs.artifact(step.step_id, name) or "")[:cap]      # noqa: E731
        labels = "\n".join(f"- `{x.value}`: {x.description}" for x in scorer.labels)
        diff = art("diff.patch", DIFF_LIMIT)
        parts = [scorer.instructions, f"## Labels\n{labels}", f"## Ticket\n{art('ticket.md', PROMPT_LIMIT)}",
                 f"## Prompt the agent received\n{art('prompt.md', PROMPT_LIMIT)}",
                 f"## The agent's reply\n{art('reply.md', PROMPT_LIMIT)}"]
        if diff:
            parts.append(f"## Diff\n{diff}")
        return "\n\n".join(parts + [ASK])

    def _record(self, scorer: ScorerSpec, step: StepRecord, outcome: tuple[str, str] | None, reason: str,
                judge_steps: list[StepRecord], manual: bool) -> dict:
        label, why = outcome if outcome else (None, reason)
        score = score_of(scorer, label) if label else None
        return {"scorer": scorer.name, "step_id": step.step_id, "run": step.run, "ticket": step.ticket,
                "role": step.role, "label": label, "score": score,
                "passed": score is not None and score >= scorer.passing_score, "reason": why,
                "judge_step": judge_steps[-1].step_id if judge_steps else None,
                "at": self._s.clock().isoformat(), "manual": manual}
