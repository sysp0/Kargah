"""Shared by every stage of a run: how a run ends, saves its work, and changes labels."""
from __future__ import annotations

import itertools
from datetime import datetime

from kargah.domain.markers import bot_comment
from kargah.domain.stages import Stage
from kargah.domain.ticket import STATUS_LABELS, Label
from kargah.orchestrator import texts
from kargah.orchestrator.context import Ctx
from kargah.orchestrator.progress import bot_markers
from kargah.orchestrator.recording import RecordingHarness
from kargah.orchestrator.services import Services
from kargah.ports.harness import Harness


class Endings:
    def __init__(self, services: Services) -> None:
        self.s = services

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

    def _post_once(self, ctx: Ctx, kind: str, text: str) -> None:
        """Post unless the bot's last comment already says exactly this (a run may have died before the label)."""
        last = [x for x in bot_markers(self.s.tracker.comments(ctx.number), ctx.bot_id) if x[1].kind != "started"]
        if not last or last[-1][1].kind != kind or text not in last[-1][0].body:
            self.s.tracker.post_comment(ctx.number, bot_comment(kind, ctx.run, text))

    def _block(self, ctx: Ctx, reason: str) -> str:
        self._post_once(ctx, "blocked", texts.blocked(reason))
        self._labels(ctx.number, add=(Label.BLOCKED,), remove=tuple(x for x in STATUS_LABELS if x != Label.BLOCKED))
        return "blocked"

    # ---- helpers --------------------------------------------------------------------------------------------
    def _save(self, ctx: Ctx, state: str, stage: Stage) -> str | None:
        ws = self.s.workspace
        title = f"#{ctx.number} {ctx.ticket.title}"
        prefix = "docs: spec " if stage is Stage.SPEC else "WIP: " if state == "incomplete" else "feat: "
        sha = ws.commit(prefix + title,
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
        ctx.harnesses = {role: wrap(s.harness_for(spec)) for role, spec in ctx.agents.items()}

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
