"""Run one ticket through build -> review -> rework until it needs a human. All state lives in git and the tracker."""
from __future__ import annotations

from kargah.domain.agents import claude_builder
from kargah.domain.config import ProjectConfig
from kargah.domain.decision import Action, Decision
from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import bot_comment
from kargah.domain.stages import Policy, Progress, Stage, next_stage
from kargah.domain.ticket import STATUS_LABELS, Comment, Label, Ticket
from kargah.domain.triage import body_has_acceptance
from kargah.orchestrator import texts
from kargah.orchestrator.closing import Closer
from kargah.orchestrator.context import Ctx
from kargah.orchestrator.feedback import already_handed_over, record_feedback, resolve_addressed
from kargah.orchestrator.interrupt import InterruptWatch
from kargah.orchestrator.planning import Planning
from kargah.orchestrator.progress import latest_feedback, latest_verdict, read_progress
from kargah.orchestrator.services import Services
from kargah.tasks.build import BuildTask
from kargah.tasks.decisions import decision_files
from kargah.tasks.prompting import build_context, sized_agent
from kargah.tasks.review import ReviewTask

MAX_STEPS = 12


class TicketRun(Planning):
    def __init__(self, services: Services) -> None:
        super().__init__(services)
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
        if Label.BUILDER_CLAUDE in ticket.labels:
            ctx.agents = claude_builder(ctx.agents)
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
            labels = s.tracker.get_ticket(ctx.number).labels
            progress = read_progress(s.workspace, comments, ctx.bot_id, ctx.cfg.base_branch, labels)
            stage = next_stage(progress, ctx.cfg.max_rework, self._policy(ctx))
            if stage is Stage.AWAIT_APPROVAL:
                return self._await_approval(ctx)
            if stage is Stage.PASS:
                return self._pass(ctx, comments)
            if progress.escalated and ctx.agents["implement"].harness != "claude":
                self._use_claude_builder(ctx)          # a run that restarts after the escalation keeps Claude
            if stage is Stage.BLOCKED:
                why = "the reviewer still found must-fix problems after the allowed rework rounds"
                if self._can_escalate(ctx, progress):
                    self._escalate(ctx, why)
                    continue
                return self._block(ctx, why)
            outcome = self._stage(ctx, stage, comments, progress)
            if outcome:
                return outcome
        return self._block(ctx, "too many steps in one run")

    def _stage(self, ctx: Ctx, stage: Stage, comments: list[Comment], progress: Progress) -> str | None:
        if stage is Stage.TRIAGE:
            if ctx.triaged:
                return self._block(ctx, "the triage report was not accepted after it was written")
            ctx.triaged = True
            return self._triage(ctx, comments)
        if stage is Stage.SPEC:
            return self._spec(ctx, comments, progress.triage)
        return self._review(ctx) if stage is Stage.REVIEW else self._build(ctx, stage, comments, progress)

    @staticmethod
    def _policy(ctx: Ctx) -> Policy:
        c = ctx.cfg
        return Policy(c.triage_policy, c.spec_policy, c.spec_min_size, body_has_acceptance(ctx.ticket.body))

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
        agent = sized_agent(ctx.agents["implement"], progress.triage)
        task = BuildTask(ctx.harnesses["implement"], s.shell, ctx.cfg, agent)
        result = task.run(ws, ctx.ticket, owners, ctx.cfg.base_branch, rework_items=items,
                          context=build_context(progress, ctx.number, ctx.stuck),
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
            self._post_once(ctx, "question", texts.question(result.question))
            self._labels(ctx.number, add=(Label.NEEDS_INFO,), remove=(Label.IN_PROGRESS,))
            return "question"
        if result.status == "limit":
            return self._limited(ctx, result.resets_at, "The build agent", Label.IN_PROGRESS, "implement")
        if result.status == "failed" and self._can_escalate(ctx, progress):
            self._escalate(ctx, f"the build failed: {result.error}")
            return None
        return self._block(ctx, f"the build failed: {result.error}")

    def _review(self, ctx: Ctx) -> str | None:
        s = self.s
        task = ReviewTask(ctx.harnesses["review"], ctx.agents["review"])
        result = task.run(s.workspace, ctx.ticket, ctx.cfg.base_branch, ctx.should_stop)
        if result.status == "interrupted":
            return self._interrupted(ctx)
        if result.status == "limit":
            return self._limited(ctx, result.resets_at, "The reviewer", Label.WAITING_REVIEW, "review")
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
