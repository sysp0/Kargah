"""Run one ticket through build -> review -> rework until it needs a human. All state lives in git and the tracker."""
from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from kargah.domain.agents import AgentSpec
from kargah.domain.config import ProjectConfig
from kargah.domain.decision import Action, Decision
from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import bot_comment
from kargah.domain.records import StepRecord
from kargah.domain.stages import Progress, Stage, next_stage
from kargah.domain.ticket import STATUS_LABELS, Comment, Label, Ticket
from kargah.orchestrator import texts
from kargah.orchestrator.closing import Closer
from kargah.orchestrator.feedback import already_handed_over, record_feedback, resolve_addressed
from kargah.orchestrator.interrupt import InterruptWatch
from kargah.orchestrator.progress import bot_markers, latest_feedback, latest_verdict, read_progress
from kargah.orchestrator.recording import RecordingHarness
from kargah.orchestrator.services import Services
from kargah.ports.harness import Harness
from kargah.tasks.build import BuildTask
from kargah.tasks.decisions import decision_files
from kargah.tasks.review import ReviewTask

MAX_STEPS = 12


@dataclass
class Stats:
    build_rounds: int = 0
    check_fails: int = 0
    reviews: int = 0
    must_fix: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    commit: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Ctx:
    ticket: Ticket
    run: str
    bot_id: int
    cfg: ProjectConfig
    branch: str
    stats: Stats = field(default_factory=Stats)
    should_stop: Callable[[], bool] | None = None      # the owner's interrupt label, polled while an agent runs
    steps: list[StepRecord] = field(default_factory=list)      # the agent calls of this run (see recording.py)
    agents: Mapping[str, AgentSpec] = field(default_factory=dict)
    builder: Harness | None = None                     # the services' harnesses, wrapped to record every call
    reviewer: Harness | None = None

    @property
    def number(self) -> int:
        return self.ticket.number


class TicketRun:
    def __init__(self, services: Services) -> None:
        self.s = services
        self._closer = Closer(services)

    # ---- entry points ---------------------------------------------------------------------------------------
    def process(self, ticket: Ticket, decision: Decision) -> str:
        s, started = self.s, self.s.clock()
        cfg = s.load_definition(s.workspace).config
        ctx = Ctx(ticket, s.run_id(), s.tracker.whoami().id, cfg, f"kargah/{ticket.number}",
                  should_stop=InterruptWatch(s.tracker, ticket.number))
        self._labels(ctx.number, add=(Label.IN_PROGRESS,), remove=tuple(x for x in STATUS_LABELS if x != Label.IN_PROGRESS))
        s.tracker.post_comment(ctx.number, bot_comment("started", ctx.run, f"{decision.action.value}: {decision.reason}."))
        s.workspace.prepare(ctx.branch, cfg.base_branch)
        definition = s.load_definition(s.workspace)     # again after the fetch: the newest default branch
        ctx.cfg, ctx.agents = definition.config, definition.agents
        if definition.problems:
            return self._block(ctx, f"the factory definition is invalid: {definition.problems[0]}")
        self._record_steps(ctx)
        if decision.action is Action.REVISE:
            record_feedback(s, ctx.number, ctx.run, s.workspace.head(), decision.items)
        outcome = self._drive(ctx)
        self._record(ctx, outcome, started)
        return outcome

    def block(self, ticket: Ticket, reason: str) -> None:
        self._block(Ctx(ticket, self.s.run_id(), 0, ProjectConfig(), f"kargah/{ticket.number}"), reason)

    # ---- the loop -------------------------------------------------------------------------------------------
    def _drive(self, ctx: Ctx) -> str:
        s = self.s
        for _ in range(MAX_STEPS):
            if ended := self._safe_point(ctx):
                return ended
            comments = s.tracker.comments(ctx.number)
            progress = read_progress(s.workspace, comments, ctx.bot_id, ctx.cfg.base_branch)
            stage = next_stage(progress, ctx.cfg.max_rework)
            if stage is Stage.PASS:
                return self._pass(ctx, comments)
            if stage is Stage.BLOCKED:
                return self._block(ctx, "the reviewer still found must-fix problems after the allowed rework rounds")
            outcome = self._review(ctx) if stage is Stage.REVIEW else self._build(ctx, stage, comments, progress)
            if outcome:
                return outcome
        return self._block(ctx, "too many steps in one run")

    def _safe_point(self, ctx: Ctx) -> str | None:
        """Between two steps: did the owner interrupt, close the issue, or merge the MR meanwhile?"""
        s = self.s
        ticket = s.tracker.get_ticket(ctx.number)
        if Label.INTERRUPT in ticket.labels:
            return self._interrupted(ctx)
        if not ticket.open:
            self._save(ctx, "incomplete", Stage.BUILD)
            self._closer.cancel(ticket, s.githost.find_mr(ctx.branch), ctx.bot_id)
            return "cancelled"
        mr = s.githost.find_mr(ctx.branch)
        if mr and mr.state == "merged":
            self._closer.complete(ticket, mr, ctx.bot_id)
            return "done"
        return None

    def _build(self, ctx: Ctx, stage: Stage, comments: list[Comment], progress: Progress) -> str | None:
        s, ws = self.s, self.s.workspace
        owners = [c for c in comments if not is_bot_comment(c, ctx.bot_id)]
        for path, content in decision_files(ctx.number, owners).items():
            ws.write_file(path, content)
        asked, _ = latest_feedback(comments, ctx.bot_id)
        verdict = latest_verdict(comments, ctx.bot_id, ws.head()) if stage is Stage.REWORK else None
        from_owner = bool(asked) and progress.feedback_open      # the owner's request outranks an older review
        items = asked if from_owner else (verdict.must_fix if verdict else ())
        task = BuildTask(ctx.builder, s.shell, ctx.cfg, ctx.agents["implement"])
        result = task.run(ws, ctx.ticket, owners, ctx.cfg.base_branch, rework_items=items,
                          rework_source="The owner" if from_owner else "The reviewer", should_stop=ctx.should_stop)
        ctx.stats.build_rounds += 1
        ctx.stats.check_fails += result.check_fails
        ctx.stats.tokens += result.tokens
        if result.status == "interrupted":
            return self._interrupted(ctx)
        if result.status == "done":
            if self._save(ctx, "complete", stage) is None and not self._close_wip(ctx, stage):
                return self._block(ctx, "the build agent made no change; a person must decide how to go on")
            return None
        self._save(ctx, "incomplete", stage)
        if result.status == "question":
            s.tracker.post_comment(ctx.number, bot_comment("question", ctx.run, texts.question(result.question)))
            self._labels(ctx.number, add=(Label.NEEDS_INFO,), remove=(Label.IN_PROGRESS,))
            return "question"
        if result.status == "limit":
            return self._limited(ctx, result.resets_at, "The build agent", Label.IN_PROGRESS)
        return self._block(ctx, f"the build failed: {result.error}")

    def _review(self, ctx: Ctx) -> str | None:
        s = self.s
        task = ReviewTask(ctx.reviewer, ctx.agents["review"])
        result = task.run(s.workspace, ctx.ticket, ctx.cfg.base_branch, ctx.should_stop)
        if result.status == "interrupted":
            return self._interrupted(ctx)
        if result.status == "limit":
            return self._limited(ctx, result.resets_at, "The reviewer", Label.WAITING_REVIEW)
        if result.status != "ok" or result.verdict is None:
            return self._block(ctx, f"the review failed: {result.error}")
        ctx.stats.reviews += 1
        ctx.stats.must_fix += len(result.verdict.must_fix)
        ctx.stats.cost_usd += result.cost_usd or 0.0
        s.tracker.post_comment(ctx.number, bot_comment("review", ctx.run, texts.review_body(result.verdict),
                                                       sha=s.workspace.head(), must_fix=len(result.verdict.must_fix)))
        return None

    # ---- endings --------------------------------------------------------------------------------------------
    def _pass(self, ctx: Ctx, comments: list[Comment]) -> str:
        s, ws = self.s, self.s.workspace
        verdict = latest_verdict(comments, ctx.bot_id, ws.head())
        assert verdict is not None
        url = s.githost.ensure_draft_mr(ctx.branch, ctx.cfg.base_branch, f"#{ctx.number} {ctx.ticket.title}", "")
        s.githost.mark_ready(ctx.branch)
        resolve_addressed(s, ctx.branch, comments, ctx.bot_id, ws.head())
        if not already_handed_over(comments, ctx.bot_id, ws.head()):       # a run may have died after this comment
            files = len(ws.changed_files(ctx.cfg.base_branch))
            s.tracker.post_comment(ctx.number, bot_comment("ready", ctx.run, texts.ready_for_human(url, verdict, files),
                                                           sha=ws.head()))
        self._labels(ctx.number, add=(Label.NEEDS_HUMAN,), remove=(Label.IN_PROGRESS, Label.WAITING_REVIEW))
        return "needs-human"

    def _limited(self, ctx: Ctx, resets_at: datetime | None, who: str, keep: Label) -> str:
        s = self.s
        if resets_at is None:
            s.tracker.post_comment(ctx.number, bot_comment("blocked", ctx.run, texts.limit(None, who)))
            self._labels(ctx.number, add=(Label.BLOCKED,), remove=(Label.IN_PROGRESS, Label.WAITING_REVIEW))
            return "limit-unknown"
        stamp = resets_at.isoformat()
        s.tracker.post_comment(ctx.number, bot_comment("limit", ctx.run, texts.limit(stamp, who), resume_at=stamp))
        self._labels(ctx.number, add=(keep,),
                     remove=tuple(x for x in (Label.IN_PROGRESS, Label.WAITING_REVIEW) if x != keep))
        return "limit"

    def _interrupted(self, ctx: Ctx) -> str:
        # no bot comment here: a comment after the owner's urgent message would hide it from the next run
        self._save(ctx, "incomplete", Stage.BUILD)
        self._labels(ctx.number, add=(Label.NEEDS_INFO,), remove=(Label.INTERRUPT, Label.IN_PROGRESS))
        return "interrupted"

    def _block(self, ctx: Ctx, reason: str) -> str:
        text = texts.blocked(reason)
        last = bot_markers(self.s.tracker.comments(ctx.number), ctx.bot_id)
        if not last or last[-1][1].kind != "blocked" or text not in last[-1][0].body:
            self.s.tracker.post_comment(ctx.number, bot_comment("blocked", ctx.run, text))   # not twice after a crash
        self._labels(ctx.number, add=(Label.BLOCKED,), remove=tuple(x for x in STATUS_LABELS if x != Label.BLOCKED))
        return "blocked"

    # ---- helpers --------------------------------------------------------------------------------------------
    def _save(self, ctx: Ctx, state: str, stage: Stage) -> str | None:
        ws = self.s.workspace
        title = f"#{ctx.number} {ctx.ticket.title}"
        sha = ws.commit(("WIP: " if state == "incomplete" else "feat: ") + title,
                        {"Kargah-Task": stage.value, "Kargah-Issue": f"#{ctx.number}", "Kargah-State": state})
        if sha:
            ws.push(ctx.branch)
            self.s.githost.ensure_draft_mr(ctx.branch, ctx.cfg.base_branch, title, f"Closes #{ctx.number}")
            ctx.stats.commit = sha
        return sha

    def _close_wip(self, ctx: Ctx, stage: Stage) -> bool:
        """The build is done with nothing new to commit: an incomplete WIP commit becomes complete (empty commit)."""
        ws = self.s.workspace
        if ws.head_state() != "incomplete":
            return False
        sha = ws.commit(f"feat: #{ctx.number} {ctx.ticket.title}", {"Kargah-Task": stage.value,
                        "Kargah-Issue": f"#{ctx.number}", "Kargah-State": "complete"}, allow_empty=True)
        ws.push(ctx.branch)
        ctx.stats.commit = sha or ""
        return True

    def _record_steps(self, ctx: Ctx) -> None:
        s, numbers = self.s, itertools.count(1)
        text = f"# #{ctx.number} {ctx.ticket.title}\n\n{ctx.ticket.body}"

        def wrap(inner: Harness) -> Harness:
            return RecordingHarness(inner, s.runs, ctx.cfg.prices, s.clock, ctx.run, ctx.number, s.workspace,
                                    ctx.cfg.base_branch, text, numbers, ctx.steps)
        ctx.builder = wrap(s.harness_for(ctx.agents["implement"]))
        ctx.reviewer = wrap(s.harness_for(ctx.agents["review"]))

    def _labels(self, number: int, add: tuple[Label, ...], remove: tuple[Label, ...]) -> None:
        for label in add:                    # add first: a crash in between leaves two labels, never none
            self.s.tracker.add_label(number, label)
        for label in remove:
            self.s.tracker.remove_label(number, label)

    def _record(self, ctx: Ctx, outcome: str, started: datetime) -> None:
        now = self.s.clock()
        st = ctx.stats
        known = [r.cost_usd for r in ctx.steps if r.cost_usd is not None]
        self.s.log.append({
            "kind": "run", "schema_version": 1, "steps": len(ctx.steps), "cost_usd": round(sum(known), 4),
            "cost_unknown_steps": len(ctx.steps) - len(known), "ticket": ctx.number, "run": ctx.run, "outcome": outcome,
            "started": started.isoformat(), "seconds": round((now - started).total_seconds(), 1),
            "commit_sha": st.commit or None, "build_rounds": st.build_rounds, "check_fails": st.check_fails,
            "reviews": st.reviews, "must_fix": st.must_fix, "tokens": st.tokens, "review_cost_usd": round(st.cost_usd, 4)})
