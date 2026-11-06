"""Run one ticket through build -> review -> rework until it needs a human. All state lives in git and the tracker."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from kargah.domain.config import ProjectConfig
from kargah.domain.decision import Decision
from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import bot_comment
from kargah.domain.stages import Stage, next_stage
from kargah.domain.ticket import Comment, Label, Ticket
from kargah.orchestrator import texts
from kargah.orchestrator.progress import latest_verdict, read_progress
from kargah.orchestrator.services import Services
from kargah.tasks.build import BuildTask
from kargah.tasks.decisions import decision_files
from kargah.tasks.review import ReviewTask

MAX_STEPS = 12
ALL_STATES = (Label.READY, Label.IN_PROGRESS, Label.NEEDS_INFO, Label.NEEDS_HUMAN, Label.WAITING_REVIEW, Label.BLOCKED)


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

    @property
    def number(self) -> int:
        return self.ticket.number


class TicketRun:
    def __init__(self, services: Services) -> None:
        self.s = services

    # ---- entry points ---------------------------------------------------------------------------------------
    def process(self, ticket: Ticket, decision: Decision) -> str:
        s, started = self.s, self.s.clock()
        cfg = s.load_config(s.workspace.root)
        ctx = Ctx(ticket, s.run_id(), s.tracker.whoami().id, cfg, f"kargah/{ticket.number}")
        self._labels(ctx.number, add=(Label.IN_PROGRESS,), remove=tuple(x for x in ALL_STATES if x != Label.IN_PROGRESS))
        s.tracker.post_comment(ctx.number, bot_comment("started", ctx.run, f"{decision.action.value}: {decision.reason}."))
        s.workspace.prepare(ctx.branch, cfg.base_branch)
        ctx.cfg = s.load_config(s.workspace.root)
        outcome = self._drive(ctx)
        self._record(ctx, outcome, started)
        return outcome

    def block(self, ticket: Ticket, reason: str) -> None:
        self._block(Ctx(ticket, self.s.run_id(), 0, ProjectConfig(), f"kargah/{ticket.number}"), reason)

    # ---- the loop -------------------------------------------------------------------------------------------
    def _drive(self, ctx: Ctx) -> str:
        s = self.s
        for _ in range(MAX_STEPS):
            if Label.INTERRUPT in s.tracker.get_ticket(ctx.number).labels:
                return self._interrupted(ctx)
            comments = s.tracker.comments(ctx.number)
            stage = next_stage(read_progress(s.workspace, comments, ctx.bot_id, ctx.cfg.base_branch), ctx.cfg.max_rework)
            if stage is Stage.PASS:
                return self._pass(ctx, comments)
            if stage is Stage.BLOCKED:
                return self._block(ctx, "the reviewer still found must-fix problems after the allowed rework rounds")
            outcome = self._review(ctx) if stage is Stage.REVIEW else self._build(ctx, stage, comments)
            if outcome:
                return outcome
        return self._block(ctx, "too many steps in one run")

    def _build(self, ctx: Ctx, stage: Stage, comments: list[Comment]) -> str | None:
        s, ws = self.s, self.s.workspace
        owners = [c for c in comments if not is_bot_comment(c, ctx.bot_id)]
        for path, content in decision_files(ctx.number, owners).items():
            ws.write_file(path, content)
        items = latest_verdict(comments, ctx.bot_id, ws.head()) if stage is Stage.REWORK else None
        result = BuildTask(s.builder, s.shell, ctx.cfg).run(ws, ctx.ticket, owners, ctx.cfg.base_branch,
                                                            rework_items=items.must_fix if items else ())
        ctx.stats.build_rounds += 1
        ctx.stats.check_fails += result.check_fails
        ctx.stats.tokens += result.tokens
        if result.status == "done":
            if self._save(ctx, "complete", stage) is None:     # no new commit would repeat the same step forever
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
        result = ReviewTask(s.reviewer, ctx.cfg).run(s.workspace, ctx.ticket, ctx.cfg.base_branch)
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
        files = len(ws.changed_files(ctx.cfg.base_branch))
        s.tracker.post_comment(ctx.number, bot_comment("ready", ctx.run, texts.ready_for_human(url, verdict, files)))
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
        self._labels(ctx.number, add=(keep,), remove=tuple(x for x in (Label.IN_PROGRESS, Label.WAITING_REVIEW) if x != keep))
        return "limit"

    def _interrupted(self, ctx: Ctx) -> str:
        # no bot comment here: a comment after the owner's urgent message would hide it from the next run
        self._save(ctx, "incomplete", Stage.BUILD)
        self._labels(ctx.number, add=(Label.NEEDS_INFO,), remove=(Label.INTERRUPT, Label.IN_PROGRESS))
        return "interrupted"

    def _block(self, ctx: Ctx, reason: str) -> str:
        self.s.tracker.post_comment(ctx.number, bot_comment("blocked", ctx.run, texts.blocked(reason)))
        self._labels(ctx.number, add=(Label.BLOCKED,), remove=(Label.IN_PROGRESS, Label.WAITING_REVIEW, Label.READY))
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

    def _labels(self, number: int, add: tuple[Label, ...], remove: tuple[Label, ...]) -> None:
        for label in remove:
            self.s.tracker.remove_label(number, label)
        for label in add:
            self.s.tracker.add_label(number, label)

    def _record(self, ctx: Ctx, outcome: str, started: datetime) -> None:
        now = self.s.clock()
        st = ctx.stats
        self.s.log.append({
            "schema_version": 1, "ticket": ctx.number, "run": ctx.run, "outcome": outcome,
            "started": started.isoformat(), "seconds": round((now - started).total_seconds(), 1),
            "commit_sha": st.commit or None, "build_rounds": st.build_rounds, "check_fails": st.check_fails,
            "reviews": st.reviews, "must_fix": st.must_fix, "tokens": st.tokens, "review_cost_usd": round(st.cost_usd, 4)})
