"""./dev stats: what each step of a package costs and finds, from the events of all runs.

Per package: minutes from first Codex round to commit, Codex rounds, failed checks per step (accept, tests, review),
cost per agent, and fix rows I<n> written for it later (bugs found after the review passed). The totals per step
show which step earns its cost: a review that never fails is paid for nothing; a step that fails often saves work.
"""

from __future__ import annotations

from collections import defaultdict

from . import events as ev
from . import plan as plan_mod
from .config import Config


def collect(cfg: Config) -> dict:
    pkgs: dict = defaultdict(lambda: {"start": None, "end": None, "rounds": 0, "fails": defaultdict(int),
                                      "calls": defaultdict(int), "cost": defaultdict(float)})
    for run in ev.list_runs(cfg.runs_dir):
        found, _ = ev.read(run.events_path)
        for e in found:
            pkg = e.get("pkg")
            if not pkg:
                continue
            p = pkgs[pkg]
            if e["type"] == "pkg" and e.get("state") == "codex":
                p["start"] = p["start"] or e["ts"]
                p["rounds"] += 1
            elif e["type"] == "pkg" and e.get("state") == "done":
                p["end"] = e["ts"]
            elif e["type"] == "result" and e.get("ok") is False:
                p["fails"][e.get("step", "?")] += 1
            elif e["type"] == "usage":
                step = e.get("step") or e.get("agent", "?")
                p["calls"][step] += 1
                p["cost"][step] += float(e.get("cost_usd") or 0)
    return pkgs


def fix_rows(cfg: Config, stage: str) -> dict[str, int]:
    plan = plan_mod.read(cfg, stage) if stage else None
    out: dict[str, int] = defaultdict(int)
    for row in plan.fixes if plan else []:
        if row.cells.get("package"):
            out[row.cells["package"]] += 1
    return out


def report(cfg: Config, stage: str = "") -> str:
    pkgs, fixes = collect(cfg), fix_rows(cfg, stage)
    done = {k: p for k, p in pkgs.items() if p["end"] and p["start"]}
    lines = ["package  minutes  rounds  failed checks              cost    fix rows later"]
    steps: dict = defaultdict(lambda: {"calls": 0, "cost": 0.0, "fails": 0})
    for name, p in sorted(done.items()):
        fails = ", ".join(f"{s} {n}" for s, n in sorted(p["fails"].items())) or "-"
        lines.append(f"{name:<8} {(p['end'] - p['start']) / 60:>7.1f}  {p['rounds']:>6}  {fails:<24} "
                     f"${sum(p['cost'].values()):>6.2f}  {fixes.get(name, 0):>6}")
        for s, n in p["calls"].items():
            steps[s]["calls"] += n
            steps[s]["cost"] += p["cost"][s]
        for s, n in p["fails"].items():
            steps[s]["fails"] += n
    lines += ["", "step         calls   cost   times it found a problem"]
    for s, v in sorted(steps.items()):
        lines.append(f"{s:<12} {v['calls']:>5} ${v['cost']:>6.2f}   {v['fails']}")
    lines.append(f"\nfix rows written after a package was built: {sum(fixes.get(k, 0) for k in done)} "
                 f"of {sum(fixes.values())}")
    return "\n".join(lines) if done else "no finished package in the runs yet"
