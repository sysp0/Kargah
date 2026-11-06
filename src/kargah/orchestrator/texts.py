"""The words of the bot's comments (short briefs, never raw logs)."""
from __future__ import annotations

from kargah.domain.review import Verdict


def question(text: str) -> str:
    return f"I need an answer before I can go on:\n\n> {text}\n\nReply in this ticket; I continue when I see your comment."


def limit(resume_at: str | None, who: str) -> str:
    if resume_at:
        return f"{who} hit its usage limit. Work so far is saved as a draft commit. I continue automatically after {resume_at}."
    return f"{who} hit its usage limit and did not say when it ends. Work so far is saved as a draft commit. " \
           "Label the ticket `ready` again when you want me to continue."


def blocked(reason: str) -> str:
    return f"I stopped and need you.\n\nWhy: {reason}\n\nWhen it is clear, comment here and label the ticket `ready`."


def review_body(verdict: Verdict) -> str:
    verdict_line = "PASS" if verdict.passed else "MUST_FIX"
    lines = [f"VERDICT: {verdict_line}"]
    lines += [f"MUST-FIX: {i}" for i in verdict.must_fix]
    lines += [f"SHOULD: {i}" for i in verdict.should]
    lines += [f"NIT: {i}" for i in verdict.nit]
    return "\n".join(lines)


def ready_for_human(mr_url: str, verdict: Verdict, files: int) -> str:
    extra = [f"- should: {i}" for i in verdict.should] + [f"- nit: {i}" for i in verdict.nit]
    notes = "\n".join(extra) if extra else "- none"
    return (f"Ready for your review: {mr_url}\n\n{files} file(s) changed. The check passed, the new tests fail without "
            f"the change, and the independent review has no must-fix.\n\nNot blocking:\n{notes}")


def feedback_body(items_text: str) -> str:
    return f"The owner asked for these changes; I am working on them:\n\n{items_text}"


def merged(url: str) -> str:
    return f"Merged: {url}"


def cancelled() -> str:
    return "Cancelled: the issue was closed. The branch and draft MR are kept."


def triage_body(report_text: str) -> str:
    return f"Triage:\n\n{report_text}"


def questions_body(questions: tuple[str, ...]) -> str:
    items = "\n".join(f"> {q}" for q in questions)
    return f"I need answers before I can go on:\n\n{items}\n\nReply in this ticket; I continue when I see your comment."


def spec_body(url: str, path: str) -> str:
    return (f"Spec ready: {url} (`{path}`). Reply `/approve` to start the build, or comment what to change.")
