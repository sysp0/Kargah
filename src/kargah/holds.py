"""Which tasks may be built now. Pure: the loop computes it from scratch every round, so no hold is forgotten.

A task is ready when it is not built, every task in its Depends is built, and no open holder holds it:

- A question or a stuck task X (an Ask): X itself until the owner's first comment after it; every task that depends on
  X, even indirectly, and every task that shares a topic of the question in Touches, until X is built. The topics are
  the answerer's ABOUT line, else all of X's Touches.
- An issue #n (a Bug: a bug, a QA failure, a plan change): the tasks its triage named as related, and the tasks that
  share one of its Touches, until it is released (its fix rows are built and its plan changes are written).
- A task P that found mid-work it needs an open holder (a Wait, `WAITS FOR: #60` or `WAITS FOR: P1`): P, until that
  holder is released.

A held task also holds what depends on it. Fix rows are never held by another task's question or by an issue: they
repair built code and go first (M03). A Depends id that is no row, or a dependency cycle, holds the task with that
reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Task:
    id: str
    depends: tuple = ()
    touches: frozenset = frozenset()
    fix: bool = False


@dataclass(frozen=True)
class Ask:
    task: str
    kind: str = "question"     # question | stuck
    open: bool = True          # no owner comment after it yet
    about: frozenset = frozenset()


@dataclass(frozen=True)
class Bug:
    number: int
    kind: str = "bug"          # bug | qa | plan-change | spec | feedback
    related: frozenset = frozenset()
    touches: frozenset = frozenset()
    released: bool = False


@dataclass(frozen=True)
class Wait:
    task: str
    target: str                # "P1" or "#60"


@dataclass(frozen=True)
class Hold:
    holder: str                # "P1 question", "#52 bug", "P4 waits for P1"
    why: str                   # "waits for your comment", "depends on P1", "shares api:/v1/segments"

    def __str__(self) -> str:
        return f"{self.holder}: {self.why}"


@dataclass
class State:
    ready: list = field(default_factory=list)     # task ids, in the given order
    held: dict = field(default_factory=dict)      # task id -> [Hold]
    queued: list = field(default_factory=list)    # not built, waits only for its Depends to be built
    notes: list = field(default_factory=list)     # what the owner should know (a wait on an unknown issue)

    def holders(self) -> list[str]:
        """Every holder that holds a task now, in first-seen order: what the loop waits for."""
        return list(dict.fromkeys(h.holder for holds in self.held.values() for h in holds))


def compute(tasks: list[Task], built: set[str], asks=(), bugs=(), waits=(),
            task_issues: dict[int, str] | None = None) -> State:
    """tasks in pick order (fix rows first, then the plan). task_issues maps an issue number to its task, so a
    `WAITS FOR: #12` on a task issue means that task."""
    by_id = {t.id: t for t in tasks}
    todo = [t for t in tasks if t.id not in built]
    plan_todo = [t for t in todo if not t.fix]
    state = State()
    direct: dict[str, list[Hold]] = {}

    def hold(task: str, holder: str, why: str) -> None:
        found = direct.setdefault(task, [])
        if not any(h.holder == holder and h.why == why for h in found):
            found.append(Hold(holder, why))

    def overlap(topics: frozenset | set, skip: str | None, holder: str) -> None:
        for t in plan_todo:
            common = sorted(t.touches & topics)
            if t.id != skip and common:
                hold(t.id, holder, f"shares {common[0]}")

    roots: dict[str, str] = {}   # unbuilt task -> holder name, whose dependents wait
    for a in asks:
        x = by_id.get(a.task)
        if x is None or x.id in built:
            continue
        name = f"{x.id} {a.kind}"
        roots[x.id] = name
        if a.open:
            hold(x.id, name, "waits for your comment")
        if not x.fix:
            overlap(a.about or x.touches, x.id, name)
    bug_by_number = {b.number: b for b in bugs}
    for b in bugs:
        if b.released:
            continue
        name = f"#{b.number} {b.kind}"
        for t in plan_todo:
            if t.id in b.related:
                hold(t.id, name, "related")
        overlap(b.touches, None, name)
    for w in waits:
        if w.task in built or w.task not in by_id:
            continue
        target = w.target
        if target.startswith("#"):
            number = int(target[1:])
            if task_issues and number in task_issues:
                target = task_issues[number]
            elif number in bug_by_number:
                if not bug_by_number[number].released:
                    hold(w.task, f"{w.task} waits for #{number}", f"#{number} {bug_by_number[number].kind} is open")
                continue
            else:
                state.notes.append(f"{w.task} waits for #{number}, which is no task or open issue of this plan; "
                                   "it is not held")
                continue
        if target not in by_id:
            state.notes.append(f"{w.task} waits for {target}, which is no row of this plan; it is not held")
        elif target not in built:
            hold(w.task, f"{w.task} waits for {target}", f"{target} is not built")

    cycles = _cycles(todo, built)
    for t in todo:
        unknown = [d for d in t.depends if d not in by_id and d not in built]
        if unknown:
            hold(t.id, f"{t.id} plan", f"depends on {unknown[0]}, which is no row of this plan")
        if t.id in cycles:
            hold(t.id, f"{t.id} plan", f"dependency cycle {cycles[t.id]}")

    memo: dict[str, list[Hold]] = {}

    def inherited(task_id: str, path: tuple = ()) -> list[Hold]:
        """Holds that reach task_id through its unbuilt dependencies."""
        if task_id in memo:
            return memo[task_id]
        out: list[Hold] = []
        t = by_id[task_id]
        for d in t.depends:
            if d in built or d not in by_id or d in path:
                continue
            if d in roots:
                out.append(Hold(roots[d], f"depends on {d}"))
            for h in direct.get(d, []):
                if h.holder != roots.get(d):
                    out.append(Hold(h.holder, f"depends on {d}"))
            for h in inherited(d, (*path, task_id)):
                out.append(Hold(h.holder, h.why if h.why.startswith("depends on") else f"depends on {d}"))
        memo[task_id] = list(dict.fromkeys(out))
        return memo[task_id]

    for t in todo:
        found = list(direct.get(t.id, []))
        if not t.fix:
            found += [h for h in inherited(t.id) if all(h.holder != x.holder for x in found)]
        if found:
            state.held[t.id] = found
        elif all(d in built for d in t.depends):
            state.ready.append(t.id)
        else:
            state.queued.append(t.id)
    return state


def _cycles(todo: list[Task], built: set[str]) -> dict[str, str]:
    """{task: "P3 > P5 > P3"} for every unbuilt task on a dependency cycle."""
    by_id = {t.id: t for t in todo}
    out: dict[str, str] = {}
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> None:
        color[n] = 1
        stack.append(n)
        for d in by_id[n].depends:
            if d not in by_id or d in built:
                continue
            if color.get(d) == 1:
                loop = stack[stack.index(d):] + [d]
                for x in loop[:-1]:
                    out.setdefault(x, " > ".join(loop))
            elif not color.get(d):
                visit(d)
        stack.pop()
        color[n] = 2

    for t in todo:
        if not color.get(t.id):
            visit(t.id)
    return out


def pick(state: State, tasks: list[Task], continuing: set[str]) -> str | None:
    """The next task: a ready fix row first (M03), then a ready task that goes on (an answered question, a helped
    stuck task, work kept from a stop), then the first ready row of the plan."""
    fixes = {t.id for t in tasks if t.fix}
    for group in ([t for t in state.ready if t in fixes], [t for t in state.ready if t in continuing], state.ready):
        if group:
            return group[0]
    return None
