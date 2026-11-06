"""The stages before the build: triage (size and acceptance) and spec (written, then approved by the owner)."""
from __future__ import annotations

from kargah.domain.inputs import is_bot_comment
from kargah.domain.markers import bot_comment
from kargah.domain.stages import Stage
from kargah.domain.ticket import STATUS_LABELS, Comment, Label
from kargah.domain.triage import format_triage
from kargah.orchestrator import texts
from kargah.orchestrator.context import Ctx
from kargah.orchestrator.endings import Endings
from kargah.tasks.spec import SpecTask
from kargah.tasks.triage import TriageTask


class Planning(Endings):
    def _triage(self, ctx: Ctx, comments: list[Comment]) -> str | None:
        s = self.s
        owners = [c for c in comments if not is_bot_comment(c, ctx.bot_id)]
        result = TriageTask(ctx.harnesses["triage"], ctx.agents["triage"]).run(s.workspace, ctx.ticket, owners,
                                                                               ctx.should_stop)
        if result.status == "done" and result.report:
            report = result.report
            s.tracker.post_comment(ctx.number, bot_comment(
                "triage", ctx.run, texts.triage_body(format_triage(report)), size=report.size,
                ambiguous=int(report.ambiguous)))
            return None
        return self._stopped_early(ctx, result.status, result.questions, result.error, result.resets_at, "triage")

    def _spec(self, ctx: Ctx, comments: list[Comment], triage) -> str | None:       # noqa: ANN001 - TriageReport | None
        s = self.s
        owners = [c for c in comments if not is_bot_comment(c, ctx.bot_id)]
        task = SpecTask(ctx.harnesses["spec"], ctx.agents["spec"])
        result = task.run(s.workspace, ctx.ticket, owners, ctx.cfg.base_branch, triage, ctx.should_stop)
        if result.status != "done":
            return self._stopped_early(ctx, result.status, result.questions, result.error, result.resets_at, "spec")
        self._save(ctx, "complete", Stage.SPEC)           # nothing to commit when a rewrite changed nothing
        url = s.githost.ensure_draft_mr(ctx.branch, ctx.cfg.base_branch, f"#{ctx.number} {ctx.ticket.title}",
                                        f"Closes #{ctx.number}")
        s.tracker.post_comment(ctx.number, bot_comment("spec", ctx.run, texts.spec_body(url, result.path),
                                                       sha=s.workspace.head()))
        return self._await_approval(ctx)

    def _await_approval(self, ctx: Ctx) -> str:
        """No new comment: the spec comment is the request."""
        self._labels(ctx.number, add=(Label.NEEDS_APPROVAL,),
                     remove=tuple(x for x in STATUS_LABELS if x != Label.NEEDS_APPROVAL))
        return "awaiting-approval"

    def _stopped_early(self, ctx: Ctx, status: str, questions: tuple[str, ...], error: str, resets_at,
                       who: str) -> str:       # noqa: ANN001 - datetime | None
        if status == "question":
            self._post_once(ctx, "question", texts.questions_body(questions))
            self._labels(ctx.number, add=(Label.NEEDS_INFO,), remove=(Label.IN_PROGRESS,))
            return "question"
        if status == "limit":
            return self._limited(ctx, resets_at, f"The {who} agent", Label.IN_PROGRESS)
        if status == "interrupted":
            return self._interrupted(ctx)
        return self._block(ctx, f"the {who} agent failed: {error}")
