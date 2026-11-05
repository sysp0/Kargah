"""Fold the event log into what the viewers show. Pure: no I/O besides reading events."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import events as ev
from .usage import Usage

FINAL = {"done", "blocked", "failed", "app_bug", "heavy"}


@dataclass
class Package:
    name: str
    state: str = "waiting"
    round: int | None = None
    started: float | None = None
    finished: float | None = None
    step_started: float | None = None
    branch: str | None = None
    commit: str | None = None
    pr: str | None = None
    note: str | None = None   # the plan-problem note of a blocked package (repo-relative path)
    message: str = ""
    last_result: str = ""
    usage: dict = field(default_factory=lambda: {"codex": Usage(), "claude": Usage()})

    def elapsed(self, at: float | None = None) -> float:
        if self.started is None:
            return 0.0
        return (self.finished or at or time.time()) - self.started


@dataclass
class View:
    run_id: str = ""
    kind: str = ""
    stage: str = ""
    started: float | None = None
    finished: float | None = None
    last_ts: float | None = None   # time of the newest event; a run that is not running stops its clocks there
    outcome: str = ""
    outcome_message: str = ""
    packages: dict = field(default_factory=dict)
    order: list = field(default_factory=list)
    totals: dict = field(default_factory=lambda: {"codex": Usage(), "claude": Usage()})
    models: dict = field(default_factory=dict)   # "claude claude-opus-5-5" -> Usage, for the cost per model
    live: deque = field(default_factory=lambda: deque(maxlen=400))
    current: str | None = None
    waiting_until: float | None = None
    findings: dict = field(default_factory=dict)
    offset: int = 0
    live_seq: int = 0
    parts: list = field(default_factory=list)       # plan parts with their packages (event `plan`)
    committed: set = field(default_factory=set)     # packages already on the branch when the plan event came
    gates: dict = field(default_factory=dict)       # part file -> qa | waiting | approved | skipped
    gate_scenarios: dict = field(default_factory=dict)   # part file -> QA scenario ids its gate runs
    issues: list = field(default_factory=list)      # kept for the viewers; the loop shows issues as tasks
    held: dict = field(default_factory=dict)        # task -> why it waits (event `plan`)
    decisions: deque = field(default_factory=lambda: deque(maxlen=200))   # `Role · item` decisions of the loop

    def _push(self, item: tuple) -> None:
        self.live.append(item)
        self.live_seq += 1

    def live_since(self, seq: int) -> list:
        new = self.live_seq - seq
        return list(self.live)[-new:] if new > 0 else []

    def pkg(self, name: str | None) -> Package:
        name = name or "-"
        if name not in self.packages:
            self.packages[name] = Package(name)
            self.order.append(name)
        return self.packages[name]

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        ts = event.get("ts", time.time())
        self.last_ts = ts
        if kind == "run_started":
            self.kind, self.stage, self.started = event.get("kind", ""), event.get("stage", ""), ts
            for name in event.get("packages") or []:
                self.pkg(name)
        elif kind == "run_finished":
            self.finished, self.outcome = ts, event.get("outcome", "")
            self.outcome_message = event.get("message", "")
        elif kind == "run_resumed":
            self.finished, self.outcome, self.outcome_message = None, "", ""
            self.gates = {k: v for k, v in self.gates.items() if v in ("approved", "skipped")}
        elif kind == "plan":
            self.parts = event.get("parts") or []
            self.committed = set(event.get("done") or [])
            self.held = event.get("held") or {}
            self.gates.update({k: v for k, v in (event.get("gates") or {}).items()})
        elif kind == "gate":
            self.gates[event.get("part", "")] = event.get("state", "")
            if event.get("scenarios"):
                self.gate_scenarios[event.get("part", "")] = list(event["scenarios"])
        elif kind == "issues":
            self.issues = event.get("issues") or []
        elif kind == "pkg":
            p = self.pkg(event.get("pkg"))
            state = event.get("state", "")
            if p.started is None:
                p.started = ts
            p.state, p.round, p.step_started = state, event.get("round"), ts
            for key in ("commit", "pr", "branch"):
                if event.get(key):
                    setattr(p, key, event[key])
            p.note = event.get("note") if state == "blocked" else None   # a resume deletes the note
            if event.get("message"):
                p.message = str(event["message"])
            if state in FINAL:
                p.finished = ts
            else:
                p.finished = None
            self.current = p.name
            self._push((ts, p.name, "state", f"{state}" + (f" (round {p.round})" if p.round is not None else "")
                              + (f": {p.message}" if state in FINAL and p.message else "")))
        elif kind == "branch":
            self.pkg(event.get("pkg")).branch = event.get("branch")
        elif kind == "usage":
            agent = event.get("agent", "codex")
            p = self.pkg(event.get("pkg"))
            p.usage.setdefault(agent, Usage()).add(event)
            self.totals.setdefault(agent, Usage()).add(event)
            self.models.setdefault(f"{agent} {event.get('model') or agent}", Usage()).add(event)
        elif kind == "result":
            p = self.pkg(event.get("pkg"))
            mark = "ok" if event.get("ok") else "FAIL"
            if event.get("step") == "triage":  # triage always follows a failed run; show its verdict instead
                mark = str(event.get("summary") or "no verdict").replace("VERDICT: ", "")
            p.last_result = f"{event.get('step')}: {mark}"
            self._push((ts, p.name, event.get("step", ""), f"{mark} {event.get('summary', '')}"))
        elif kind == "findings":
            self.findings[(event.get("pkg"), event.get("round"))] = event.get("text", "")
            first = (event.get("text") or "").splitlines()[:1]
            self._push((ts, event.get("pkg"), "findings", first[0] if first else ""))
        elif kind == "live":
            self._push((ts, event.get("pkg"), event.get("step", ""), event.get("text", "")))
        elif kind == "limit_wait":
            self.waiting_until = event.get("until")
            agent = str(event.get("agent") or "codex").capitalize()
            self._push((ts, event.get("pkg"), "limit", f"{agent} usage limit: waiting {event.get('seconds')}s"))
        elif kind == "decision":
            self._push((ts, event.get("item"), event.get("role", "").lower(), event.get("text", "")))
            self.decisions.append(event)
        elif kind == "limit_done":
            self.waiting_until = None
        elif kind == "note":
            self._push((ts, event.get("pkg"), "note", event.get("text", "")))

    def refresh(self, path: Path) -> bool:
        found, self.offset = ev.read(path, self.offset)
        for event in found:
            self.apply(event)
        return bool(found)


def load(run: ev.Run) -> View:
    view = View(run_id=run.id)
    view.refresh(run.events_path)
    return view


def duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


ISSUE_ICON = {"waiting": "⏳", "needs-info": "❓", "question": "❓", "decide": "⚖", "fixing": "🔧", "fixed": "✔",
              "closed": "☑"}
PART_STATES = ("approved", "skipped", "waiting", "qa")


def issue_counts(found: list[dict]) -> str:
    """"⏳1 🔧1 ✔2" in the order of ISSUE_ICON; ❓ counts both needs-info and question."""
    counts: dict[str, int] = {}
    for issue in found:
        icon = ISSUE_ICON.get(issue.get("status", ""), "?")
        counts[icon] = counts.get(icon, 0) + 1
    return " ".join(f"{icon}{counts[icon]}" for icon in dict.fromkeys(ISSUE_ICON.values()) if icon in counts)


def tree(view: View) -> list[dict]:
    """Rows of the plan tree: part, then its packages with their issues under them, then the part's QA scenarios.

    Empty when the run has no plan event (a single plan file, a QA run): the viewers then list packages flat.
    Each row: kind (part | pkg | issue | group), key, depth, label, title, state, detail, counts, and for pkg rows the
    Package, for issue rows the issue."""
    if not view.parts:
        return []
    rows: list[dict] = []
    placed: set[str] = set()
    shown: set[int] = set()

    def package(name: str) -> Package:
        if name in view.packages:
            return view.packages[name]
        return Package(name, state="done" if name in view.committed else "held" if name in view.held else "waiting",
                       message="; ".join(view.held.get(name, [])))

    def issue_row(issue: dict, depth: int) -> dict:
        shown.add(issue.get("number"))
        built = view.packages.get(issue.get("row") or "")
        live = built and built.state not in FINAL and built.state != "waiting"
        state = f"{issue.get('status')} · {built.state}" if live else issue.get("status", "")
        if built:
            placed.add(built.name)
        return {"kind": "issue", "key": f"issue:{issue.get('number')}", "depth": depth,
                "label": f"#{issue.get('number')}", "title": issue.get("title", ""), "state": state,
                "icon": ISSUE_ICON.get(issue.get("status", ""), "?"), "issue": issue, "pkg": built,
                "detail": " · ".join(x for x in (issue.get("row"), issue.get("author") and f"@{issue['author']}") if x),
                "counts": ""}

    for part in view.parts:
        name = part.get("file", "")
        ids = [p.get("id") for p in part.get("packages") or []]
        pkgs = [package(p) for p in ids]
        mine = [i for i in view.issues if i.get("part") == name]
        done = sum(1 for p in pkgs if p.state == "done")
        state = view.gates.get(name, "")
        if state == "waiting":
            state = "waiting for test"
        elif state == "qa":
            state = "QA running"
        elif not state:
            active = any(p.state not in FINAL and p.state != "waiting" for p in pkgs)
            state = "done" if pkgs and done == len(pkgs) else "building" if active or done else "not started"
        rows.append({"kind": "part", "key": f"part:{name}", "depth": 0, "label": name, "title": part.get("title", ""),
                     "state": state, "detail": f"{done}/{len(pkgs)}", "counts": issue_counts(mine)})
        for pid, p in zip(ids, pkgs, strict=True):
            placed.add(pid)
            title = next((x.get("title", "") for x in part.get("packages") or [] if x.get("id") == pid), "")
            under = [i for i in mine if i.get("package") == pid]
            rows.append({"kind": "pkg", "key": pid, "depth": 1, "label": pid, "title": title, "state": p.state,
                         "pkg": p, "detail": p.commit or p.message, "counts": issue_counts(under)})
            rows += [issue_row(i, 2) for i in under]
        rows += [issue_row(i, 1) for i in mine if i.get("number") not in shown]
        for sid in view.gate_scenarios.get(name, []):
            placed.add(sid)
            p = package(sid)
            rows.append({"kind": "pkg", "key": sid, "depth": 1, "label": sid, "title": "QA scenario", "state": p.state,
                         "pkg": p, "detail": p.commit or p.message, "counts": ""})
    rest = [i for i in view.issues if i.get("number") not in shown]
    others = [n for n in view.order if n not in placed and n != "-" and not n.startswith("#")]
    if rest or others:
        rows.append({"kind": "group", "key": "group:other", "depth": 0, "label": "other", "title": "",
                     "state": "", "detail": "", "counts": issue_counts(rest)})
        for n in others:
            p = view.packages[n]
            rows.append({"kind": "pkg", "key": n, "depth": 1, "label": n, "title": "", "state": p.state, "pkg": p,
                         "detail": p.commit or p.message, "counts": ""})
        rows += [issue_row(i, 1) for i in rest]
    return rows
