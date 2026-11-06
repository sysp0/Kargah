"""Build task (implement and rework): the agent works, then the check and the proof must pass."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from kargah.domain.config import ProjectConfig
from kargah.domain.review import parse_question
from kargah.domain.ticket import Comment, Ticket
from kargah.ports.harness import Harness, HarnessRequest
from kargah.ports.shell import Shell
from kargah.ports.workspace import Workspace
from kargah.tasks.prompting import conversation, render
from kargah.tasks.proof import Proof

Status = Literal["done", "question", "limit", "failed"]


@dataclass
class BuildResult:
    status: Status
    text: str = ""
    question: str = ""
    error: str = ""
    resets_at: datetime | None = None
    check_fails: int = 0
    tokens: int = 0
    notes: list[str] = field(default_factory=list)


class BuildTask:
    def __init__(self, harness: Harness, shell: Shell, config: ProjectConfig) -> None:
        self._harness, self._shell, self._cfg = harness, shell, config

    def run(self, ws: Workspace, ticket: Ticket, owner_comments: Sequence[Comment], base: str, *,
            rework_items: Sequence[str] = ()) -> BuildResult:
        values = dict(number=ticket.number, title=ticket.title, body=ticket.body, check_command=self._cfg.check_command,
                      conversation=conversation(owner_comments), progress="", must_fix="\n".join(f"- {i}" for i in rework_items))
        prompt = render("rework" if rework_items else "build", **values)
        result = BuildResult("failed")
        for _ in range(1 + self._cfg.max_fix_rounds):
            reply = self._harness.run(HarnessRequest("build", prompt, ws.root, self._cfg.build_timeout_seconds,
                                                     self._cfg.build_model))
            result.tokens += (reply.tokens_in or 0) + (reply.tokens_out or 0)
            if reply.limited:
                return BuildResult("limit", resets_at=reply.resets_at, check_fails=result.check_fails,
                                   tokens=result.tokens)
            if not reply.ok:
                return BuildResult("failed", error=reply.error, check_fails=result.check_fails, tokens=result.tokens)
            if question := parse_question(reply.text):
                return BuildResult("question", question=question, check_fails=result.check_fails, tokens=result.tokens)
            problem = self._problem(ws, base, guarded=not rework_items)
            if problem is None:
                return BuildResult("done", text=reply.text, check_fails=result.check_fails, tokens=result.tokens)
            result.check_fails += 1
            result.error = problem
            prompt = f"The factory ran its gates on your work and they failed:\n\n{problem}\n\nFix exactly this. " \
                     f"Same rules as before; end with a short summary or a `QUESTION:` line."
        return BuildResult("failed", error=result.error, check_fails=result.check_fails, tokens=result.tokens)

    def _problem(self, ws: Workspace, base: str, *, guarded: bool) -> str | None:
        check = self._shell.run(self._cfg.check_command, ws.root, self._cfg.build_timeout_seconds)
        if check.returncode != 0:
            return f"`{self._cfg.check_command}` failed:\n{check.tail}"
        if guarded:
            proof = Proof(ws, self._shell, self._cfg).check(base)
            if not proof.ok:
                return f"proof failed: {proof.reason}"
        return None
