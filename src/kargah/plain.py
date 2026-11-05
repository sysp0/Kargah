"""Text views: `dev runs`, `dev usage`, and `dev watch --plain` (no TTY or no textual)."""

from __future__ import annotations

import sys
import time

from . import events as ev
from .model import View, duration, load, tree
from .usage import Usage, short

ICON = {"done": "✓", "failed": "✗", "blocked": "■", "app_bug": "!", "waiting": "·", "held": "⏸"}


def usage_line(name: str, u: Usage) -> str:
    pct = u.cache_pct
    cache = f"{pct:.0f}%" if pct is not None else "-"
    cost = f"  ${u.cost_usd:.2f}" if u.cost_usd else ""
    reasoning = f"  reason {short(u.reasoning)}" if u.reasoning else ""
    return (f"{name:<7} calls {u.calls:<3} in {short(u.input):>6}  cached {short(u.cached):>6} ({cache:>4})  "
            f"cache-write {short(u.cache_write):>6}  out {short(u.output):>6}{reasoning}{cost}")


def summary(view: View, now: float | None = None) -> str:
    now = now or time.time()
    end = view.finished or now
    head = f"run {view.run_id}  {view.kind} {view.stage}  elapsed {duration(end - (view.started or end))}"
    if view.outcome:
        head += f"  outcome {view.outcome}"
    lines = [head]
    for node in tree(view):
        indent = "  " * (node["depth"] + 1)
        p = node.get("pkg")
        if node["kind"] in ("part", "group"):
            row = f"{indent}{node['label']}  {node['state']}  {node['detail']}  {node['counts']}  {node['title']}"
        elif node["kind"] == "issue":
            row = f"{indent}{node['icon']} {node['label']} {node['state']}  {node['detail']}  {node['title']}"
        else:
            row = f"{indent}{ICON.get(p.state, '▶')} {node['label']:<6} {p.state:<9} {p.last_result:<16} " \
                  f"{p.commit or p.message or ''}  {node['counts']}"
        lines.append(row.rstrip()[:160])
    for name in [] if view.parts else view.order:
        p = view.packages[name]
        icon = ICON.get(p.state, "▶")
        rnd = f"r{p.round}" if p.round is not None else "  "
        extra = p.commit or p.message
        row = f"  {icon} {name:<8} {p.state:<9} {rnd:<3} {duration(p.elapsed(now)):>7}  {p.last_result:<16} {extra}"
        lines.append(row[:160])
    lines.append(usage_line("codex", view.totals.get("codex", Usage())))
    lines.append(usage_line("claude", view.totals.get("claude", Usage())))
    if view.waiting_until and not view.finished:
        lines.append(f"waiting on a usage limit for {duration(view.waiting_until - now)}")
    if view.outcome_message:
        lines.append(view.outcome_message)
    return "\n".join(lines)


def runs_table(runs: list[ev.Run]) -> str:
    rows = []
    for run in runs:
        view = load(run)
        status = view.outcome or ("running" if run.alive() else "stopped")
        pkgs = ",".join(view.order)
        claude = view.totals.get("claude", Usage())
        codex = view.totals.get("codex", Usage())
        rows.append(f"{run.id:<34} {status:<8} {pkgs[:30]:<30} codex {short(codex.input + codex.cached):>6}"
                    f"  claude ${claude.cost_usd:.2f}")
    return "\n".join(rows) if rows else "no runs yet"


def usage_table(view: View) -> str:
    lines = [f"run {view.run_id}"]
    for name in view.order:
        p = view.packages[name]
        lines.append(f"[{name}]")
        for agent, u in p.usage.items():
            if u.calls or u.input or u.output:
                lines.append("  " + usage_line(agent, u))
    lines.append("[total]")
    for agent, u in view.totals.items():
        lines.append("  " + usage_line(agent, u))
    return "\n".join(lines)


def watch(run: ev.Run, interval: float = 3.0, heartbeat: float = 30.0, out=sys.stdout) -> None:
    """Print the summary when new events arrive, and at least every `heartbeat` seconds."""
    view = View(run_id=run.id)
    printed = 0.0
    while True:
        changed = view.refresh(run.events_path)
        if changed or time.time() - printed >= heartbeat:
            live = [f"    {e[1] or '-'} {e[2]}: {e[3]}" for e in list(view.live)[-3:]]
            print(summary(view) + ("\n" + "\n".join(live) if live else "") + "\n", file=out, flush=True)
            printed = time.time()
        if view.finished or (not run.alive() and view.started):
            return
        time.sleep(interval)
