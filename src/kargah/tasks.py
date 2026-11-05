"""Task issues: one issue per plan row, and what devchain reads back from the comments on them.

Every comment and body devchain writes ends with a hidden marker `<!-- devchain:<kind> key=value ... -->`; a comment
without one is a person's. The state of a task is never stored elsewhere: it follows from the plan (the row), the
commits (trailer `Package:`), and these markers and comments:

- question / stuck: devchain asked; the task waits until the first person's comment after it (the answer or the help).
- waits: the task found mid-work it needs an open issue or task; it waits until that holder is released.
- release: the task was released; markers before it no longer hold it.
- triage: devchain read an issue; the marker names its kind, related tasks, topics and fix rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .forge import Comment, Issue
from .plan import Plan, Row

MARK_RE = re.compile(r"<!--\s*devchain:(\w[\w-]*)((?:\s+[\w-]+=[^\s>]*)*)\s*-->")
ASKS = ("question", "stuck")
STATE_LABELS = {"task": "0052cc", "in-progress": "1d76db", "done": "0e8a16", "question": "d876e3", "held": "fbca04",
                "stuck": "b60205", "to-verify": "5319e7", "help": "b60205", "devchain-status": "c5def5",
                "feedback": "d93f0b", "qa": "d93f0b", "plan-change": "0e8a16", "spec": "0e8a16"}


def _value(v) -> str:
    text = ",".join(map(str, v)) if isinstance(v, (list, tuple, set)) else str(v)
    return re.sub(r"[\s>]+", "_", text)   # a space or > would end the mark early: the comment would read as a person's


def mark(name: str, /, **values) -> str:
    parts = " ".join(f"{k}={_value(v)}" for k, v in values.items() if v not in (None, "", [], (), set()))
    return f"<!-- devchain:{name}{' ' + parts if parts else ''} -->"


def marker(text: str) -> tuple[str, dict] | None:
    """(kind, {key: value}) of the last devchain marker in text, or None."""
    found = MARK_RE.findall(text or "")
    if not found:
        return None
    kind, rest = found[-1]
    return kind, dict(p.split("=", 1) for p in rest.split())


def listed(value: str) -> list[str]:
    return [x for x in (value or "").split(",") if x]


def is_mine(comment: Comment) -> bool:
    return marker(comment.body) is not None


def people(issue: Issue, authors: list[str]) -> list[Comment]:
    """Comments by people (no devchain marker), from the allowed authors when the list is not empty."""
    return [c for c in issue.comments if not is_mine(c) and (not authors or c.author in authors)]


def unread(issue: Issue, authors: list[str]) -> list[Comment]:
    """People's comments after devchain's last comment: devchain has not answered them yet."""
    last = max((i for i, c in enumerate(issue.comments) if is_mine(c)), default=-1)
    return [c for c in issue.comments[last + 1:] if not is_mine(c) and (not authors or c.author in authors)]


def last_mark(issue: Issue, kinds: tuple, after: tuple = ()) -> tuple[int, str, dict] | None:
    """(index, kind, values) of the newest comment marker of one of kinds, not older than a marker of `after`."""
    floor = max((i for i, c in enumerate(issue.comments) if (m := marker(c.body)) and m[0] in after), default=-1)
    for i in range(len(issue.comments) - 1, floor, -1):
        m = marker(issue.comments[i].body)
        if m and m[0] in kinds:
            return i, m[0], m[1]
    return None


def ask(issue: Issue, authors: list[str]) -> tuple[str, bool, list[str], str] | None:
    """(kind, still open, about topics, the people's answer so far) of the task's newest question or stuck mark,
    unless a later `done` closed it."""
    found = last_mark(issue, ASKS, after=("done",))
    if not found:
        return None
    i, kind, values = found
    answers = [c.body.strip() for c in issue.comments[i + 1:]
               if not is_mine(c) and (not authors or c.author in authors)]
    return kind, not answers, listed(values.get("about", "")), "\n\n".join(answers)


def wait(issue: Issue) -> str | None:
    """The holder a task waits for (#60 or P1), from its newest waits mark after the last release."""
    found = last_mark(issue, ("waits",), after=("release", "done"))
    return found[2].get("on") if found else None


def triage(issue: Issue) -> dict | None:
    """The newest triage mark of an issue: kind, related, touches, rows."""
    found = last_mark(issue, ("triage",))
    if not found:
        return None
    values = found[2]
    return {"kind": values.get("kind", ""), "related": listed(values.get("related", "")),
            "touches": listed(values.get("touches", "")), "rows": listed(values.get("rows", ""))}


def body_mark(issue: Issue) -> dict:
    m = marker(issue.body)
    return m[1] if m and m[0] == "task" else {}


def index(issues: list[Issue], stage: str) -> dict[str, Issue]:
    """{row id: its task issue} of this plan, from the body marks (the oldest issue wins a duplicate)."""
    out: dict[str, Issue] = {}
    for issue in sorted(issues, key=lambda i: i.number):
        values = body_mark(issue)
        if values.get("plan") == stage and values.get("id") and values["id"] not in out:
            out[values["id"]] = issue
    return out


def title(row: Row) -> str:
    return f"{row.id}: {' '.join(row.title.split())}"[:240]


def body(plan: Plan, row: Row) -> str:
    cells = [("Title", row.title), ("Depends", ", ".join(row.depends) or "-"),
             *[(name.capitalize(), row.cells[key]) for key, name in
               (("touches", "touches"), ("files", "files"), ("acceptance", "acceptance"), ("risk", "risk"),
                ("you see", "you see")) if row.cells.get(key)]]
    lines = [f"Task **{row.id}** of plan `{plan.stage}`, part `{row.part}`.", "", "| | |", "|---|---|",
             *[f"| {k} | {v} |" for k, v in cells], "",
             f"The plan file `{plan.path_of(row.id)}` is the source; devchain writes this text again when the row "
             "changes. Comment here to answer a question, help a stuck task, or ask for a change of this task.",
             "", mark("task", plan=plan.stage, id=row.id, hash=row.hash)]
    return "\n".join(lines)


@dataclass
class Trace:
    """<plan folder>/trace.md: one line per change of a row, with its cause; the comment on a task issue quotes it."""

    path: object

    def add(self, row_id: str, cause: str, date: str) -> None:
        if not self.path.is_file():
            self.path.write_text("# Why rows changed\n\nOne line per change of a row: date, row, cause. Written by "
                                 "devchain and the planning agents; the task issue quotes it.\n\n", encoding="utf-8")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(f"- {date} {row_id}: {' '.join(cause.split())[:600]}\n")

    def last(self, row_id: str) -> str:
        if not self.path.is_file():
            return ""
        lines = [x for x in self.path.read_text(encoding="utf-8").splitlines()
                 if re.match(rf"^-\s+\S+\s+{re.escape(row_id)}\b", x)]
        return lines[-1].lstrip("- ").strip() if lines else ""
