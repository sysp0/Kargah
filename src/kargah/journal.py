"""The loop's decision log: one line per decision, in the run folder (loop.log) and per plan
(.devchain/logs/<plan>.log), and a `decision` event for the viewers.

A line: `2026-10-21 12:30:01  Pick · P12  ready (deps P10 built)`. Every agent call adds a line with its role,
model, duration, tokens, cost, exit code and log path; an error adds a line and its traceback file.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .events import Run

ROLES = {"codex": "Build", "review": "Review", "planfix": "Plan check", "triage": "Triage", "ui_design": "UI design",
         "accept": "Checks", "tests": "Checks", "playwright": "Browser", "reproduce": "Reproduce"}
LINE_RE = re.compile(r"^(\S+ \S+)\s{2}(.+?) · (\S+)\s{2}(.*)$")


def stamp(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or time.time()))


class Journal:
    def __init__(self, run: Run, plan_log: Path):
        self.run, self.plan_log = run, plan_log
        plan_log.parent.mkdir(parents=True, exist_ok=True)
        self.started: dict[tuple, float] = {}
        run.listeners.append(self.on_event)

    def decision(self, role: str, item: str, text: str, **fields) -> None:
        line = f"{stamp()}  {role} · {item}  {' '.join(str(text).split())}\n"
        for path in (self.run.dir / "loop.log", self.plan_log):
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        self.run.emit("decision", role=role, item=item, text=text, **fields)

    def error(self, item: str, text: str, trace: str) -> Path:
        path = self.run.dir / f"error-{int(time.time())}.txt"
        path.write_text(trace, encoding="utf-8")
        self.decision("Error", item, f"{text} (traceback {path})")
        return path

    def on_event(self, event: dict) -> None:
        """Agent calls: remember when each step started; a usage event closes the call with its numbers."""
        kind = event.get("type")
        if kind == "pkg":
            self.started[(event.get("pkg"), event.get("state"))] = event.get("ts", time.time())
        elif kind == "usage":
            agent = event.get("agent", "")
            step = event.get("step") or ("codex" if agent == "codex" else "review")
            began = self.started.get((event.get("pkg"), step)) or max(
                [t for (p, _), t in self.started.items() if p == event.get("pkg")] or [time.time()])
            cost = f" ${event['cost_usd']:.2f}" if event.get("cost_usd") else ""
            line = (f"{stamp()}  Call · {event.get('pkg') or '-'}  {ROLES.get(step, step)} {agent} "
                    f"{event.get('model') or ''} {int(time.time() - began)}s in {event.get('input', 0)} "
                    f"cached {event.get('cached', 0)} out {event.get('output', 0)}{cost} exit "
                    f"{event.get('rc', '?')} log {event.get('log') or '-'}\n")
            for path in (self.run.dir / "loop.log", self.plan_log):
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
        elif kind == "limit_wait":
            self.decision("Limit", event.get("pkg") or "-", f"{event.get('agent')} usage limit: waiting "
                                                            f"{event.get('seconds')}s")


def read(path: Path, item: str | None = None, role: str | None = None, errors: bool = False,
         last: int = 80) -> list[str]:
    """Lines of a log, filtered: one task (P12, #52), one role (Hold, Pick, Call, ...), or only errors."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        if item and m.group(3) != item and item not in m.group(4).split():
            continue
        if role and m.group(2).lower() != role.lower():
            continue
        if errors and m.group(2) not in ("Error", "Help"):
            continue
        out.append(line)
    return out[-last:]
