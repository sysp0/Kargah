"""`kargah bench`: run fixed tasks with several configurations and compare them; no tracker, no push, no MR."""
from __future__ import annotations

import itertools
import json
from dataclasses import replace
from pathlib import Path

from kargah.adapters.jsonl_log import JsonlLog
from kargah.domain.agents import Definition
from kargah.domain.bench import BenchTask, Configuration, Suite, recommend, summarize
from kargah.domain.records import StepRecord
from kargah.domain.scoring import ScoreLabel, ScorerSpec
from kargah.domain.ticket import Ticket
from kargah.errors import KargahError
from kargah.orchestrator.lock import RunLock
from kargah.orchestrator.recording import RecordingHarness
from kargah.orchestrator.scoring import Scoring
from kargah.orchestrator.services import Services
from kargah.tasks.build import BuildTask

CORRECTNESS = (ScoreLabel("pass", 1.0, "Meets every success criterion."),
               ScoreLabel("partial", 0.5, "Meets some of them, or breaks something else."),
               ScoreLabel("fail", 0.0, "Does not meet them."))


class BenchRunner:
    def __init__(self, services: Services, workdir: Path, state_dir: Path) -> None:
        self._s, self._dir, self._lock = services, workdir / "bench", state_dir / "run.lock"

    def run(self, definition: Definition, suite_name: str, only: str = "") -> str:
        """The text report, or "busy" when the factory (or another benchmark) holds the lock."""
        suite = definition.suites.get(suite_name)
        if suite is None:
            raise KargahError(f"no benchmark suite '{suite_name}' on the default branch (known: "
                              f"{', '.join(definition.suites) or 'none'})")
        configs = [c for c in suite.configurations if only in ("", c.name)]
        if not configs:
            raise KargahError(f"suite '{suite_name}' has no configuration '{only}'")
        with RunLock(self._lock) as lock:
            if not lock.acquired:
                return "busy"
            results = [self._trial(definition, suite, c, t, rep) for c in configs for t in suite.tasks
                       for rep in range(1, suite.repetitions + 1)]
        return format_summary(results)

    def _trial(self, definition: Definition, suite: Suite, config: Configuration, task: BenchTask, rep: int) -> dict:
        s, trial = self._s, self._s.run_id()
        agent = replace(definition.agents["implement"], harness=config.harness, model=config.model, models_by_size={})
        steps: list[StepRecord] = []
        text = f"# {task.title}\n\n{task.body}"
        started = s.clock()
        with s.workspace.worktree(task.start_sha, self._dir / suite.name / trial / "wt") as ws:
            harness = RecordingHarness(s.harness_for(agent), s.runs, definition.config.prices, s.clock, trial, 0, ws,
                                       task.start_sha, text, itertools.count(1), steps)
            built = BuildTask(harness, s.shell, definition.config, agent).run(
                ws, Ticket(0, task.title, task.body, frozenset()), (), task.start_sha)
        if built.status == "limit":
            raise KargahError("the builder hit a usage limit; run the benchmark again later")
        correctness, scores = self._grade(definition, suite, task, steps)
        costs = [r.cost_usd for r in steps if r.cost_usd is not None]
        record = {"suite": suite.name, "configuration": config.name, "task": task.name, "rep": rep,
                  "status": built.status, "seconds": round((s.clock() - started).total_seconds(), 1),
                  "tokens": sum((r.tokens_in or 0) + (r.tokens_out or 0) for r in steps),
                  "cost_usd": round(sum(costs), 6) if costs and len(costs) == len(steps) else None,
                  "gates_passed": built.status == "done", "correctness": correctness, "scores": scores,
                  "definition_hash": suite.definition_hash, "at": s.clock().isoformat()}
        JsonlLog(self._dir / "results.jsonl").append(record)
        return record

    def _grade(self, definition: Definition, suite: Suite, task: BenchTask,
               steps: list[StepRecord]) -> tuple[float | None, dict[str, float | None]]:
        s, scoring = self._s, Scoring(self._s)
        if not steps or not (s.runs.artifact(steps[-1].step_id, "diff.patch") or "").strip():
            return 0.0, {}                  # nothing was changed: nothing to judge
        last = steps[-1]
        judge = definition.scorers.get(suite.scorers[0]) if suite.scorers else None
        harness, model = (judge.harness, judge.model) if judge else ("claude", "claude-haiku-5-5")
        correct = ScorerSpec("correctness", "success criteria", ("implement",), harness, model, 1.0, 0, False,
                             CORRECTNESS, "Judge whether the change meets these success criteria, and only these:\n\n"
                                          f"{task.success_criteria}")
        scores: dict[str, float | None] = {}
        for scorer in [correct, *(definition.scorers[n] for n in suite.scorers)]:
            judged = scoring.judge(definition, scorer, scoring.prompt_for(scorer, last), 0, f"# {task.title}")
            if judged is None:
                raise KargahError("a judge hit a usage limit; run the benchmark again later")
            scores[scorer.name] = next((x.score for x in scorer.labels if x.value == judged.label), None)
        return scores.pop("correctness"), scores


def format_summary(results: list[dict]) -> str:
    lines = ["configuration: n, mean correctness, pass rate, mean cost (USD), median seconds"]
    for x in summarize(results):
        cost = f"{x.mean_cost:.4f}" if x.mean_cost is not None else "unknown"
        lines.append(f"{x.configuration}: {x.n}, {x.mean_correctness:.2f}, {x.pass_rate:.2f}, {cost}, "
                     f"{x.median_seconds:.0f}")
    lines.append(f"recommended: {recommend(summarize(results)) or 'none'}")
    return "\n".join(lines)


def add_task(workdir_steps: list[StepRecord], artifact, suite: str, step_id: str, repo: Path) -> Path:      # noqa: ANN001
    """Turn a real step into a benchmark task. The owner writes `success_criteria` (it starts as TODO)."""
    step = next((r for r in workdir_steps if r.step_id == step_id), None)
    if step is None or not step.base_sha:
        raise KargahError(f"step '{step_id}' is unknown or has no base_sha")
    ticket = artifact(step_id, "ticket.md")
    if not ticket:
        raise KargahError(f"step '{step_id}' has no ticket.md")
    title = ticket.splitlines()[0].removeprefix("# ").strip()
    target = repo / ".kargah" / "benchmarks" / suite / "tasks" / f"from-{step_id}.toml"
    if target.exists():
        raise KargahError(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    quote = lambda text: json.dumps(text, ensure_ascii=False)      # noqa: E731 - JSON strings are valid TOML strings
    target.write_text(f"title = {quote(title)}\nbody = {quote(ticket)}\nsuccess_criteria = \"TODO\"\n"
                      f"start_sha = {quote(step.base_sha)}\nsource_step = {quote(step_id)}\n", encoding="utf-8")
    return target
