"""Triage and plan rewrite of one issue (Opus): a bug, a QA failure, a plan change, a spec change, or the owner's
comment on a task issue.

The agent reads the issue with its whole conversation and the list of rows (built or not, Depends, Touches). It may
write only the plan folder: fix rows I<n> in issues.md for built code, rewritten or new rows for what is not built,
and one line per changed row in trace.md. Python checks every edit: no file outside the folder, no built row
changed or removed, fix rows only of this issue. It commits the plan change, comments on the issue with a hidden
triage mark (kind, related tasks, topics, fix rows) and labels it; the loop holds the related tasks from that mark.
"""

from __future__ import annotations

import re
import time

from . import agents, gitops
from . import plan as plan_mod
from .config import Config
from .events import Run
from .forge import Issue, Tracker
from .plan_tasks import Trace, mark, marker

KINDS = ("FIX", "PLAN", "QUESTION", "NOTE")
ISSUES_HEAD = ("# Fix rows of plan {stage}\n\nWritten by devchain's triage from issues. A fix row I<n> repairs built "
               "code; it runs before the next row of the plan.\n\n"
               "| Pn | Title | Depends | Touches | files | acceptance | issue | part | package | seed |\n"
               "|---|---|---|---|---|---|---|---|---|---|\n")


def issue_text(issue: Issue, authors: list[str]) -> str:
    lines = [f"# Issue #{issue.number}: {issue.title}", f"Labels: {', '.join(sorted(issue.labels)) or '-'}",
             f"Author: {issue.author}", "", "## Body", issue.body.strip() or "-", "", "## Conversation (oldest first)"]
    for c in issue.comments:
        mine = marker(c.body) is not None
        if not mine and authors and c.author not in authors:
            continue   # a stranger's text never reaches the model
        lines += [f"### {'devchain' if mine else c.author}", c.body.strip(), ""]
    return "\n".join(lines)


def rows_text(plan: plan_mod.Plan, built: set[str]) -> str:
    lines = ["| Row | Built | Part | Depends | Touches | Title |", "|---|---|---|---|---|---|"]
    for r in [*plan.rows, *plan.fixes]:
        lines.append(f"| {r.id} | {'built' if r.id in built else 'not built'} | {r.part} | "
                     f"{', '.join(r.depends) or '-'} | {', '.join(sorted(r.touches)) or '-'} | {r.title} |")
    return "\n".join(lines)


def parse(text: str) -> dict | None:
    lines = text.strip().splitlines()
    m = re.match(r"^TRIAGE:\s*(FIX|PLAN|QUESTION|NOTE)\b", lines[0].strip()) if lines else None
    if not m:
        return None
    out = {"kind": m.group(1), "related": [], "touches": [], "comment": ""}
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            out["comment"] = "\n".join(lines[i + 1:]).strip()
            break
        key, _, value = line.partition(":")
        if key.strip().upper() == "RELATED":
            out["related"] = plan_mod.ID_RE.findall(value)
        elif key.strip().upper() == "TOUCHES":
            out["touches"] = [t.strip(" `").replace(" ", "") for t in re.split(r"[,;]", value)
                              if t.strip(" `-") and t.strip(" `").lower() != "none"]
    return out if out["comment"] else None


class Triage:
    def __init__(self, cfg: Config, run: Run, stage: str, tracker: Tracker, journal, authors: list[str]):
        self.cfg, self.run, self.stage, self.tracker, self.journal = cfg, run, stage, tracker, journal
        self.authors = authors
        self.folder = plan_mod.folder_of(cfg, stage)
        self.model = cfg.get("models.triage", "claude-opus-5-5")
        self.max_files = int(cfg.get("issues.fix_max_files", 5))

    def run_issue(self, issue: Issue, mode: str, plan: plan_mod.Plan, built: set[str], task: str = "") -> dict | None:
        """Triage one issue; the parsed verdict, or None when the agent failed (the loop tries again later)."""
        from .feature import _restore, _snapshot, render

        root, n = self.cfg.root, issue.number
        d = self.run.pkg_dir(f"issue-{n}")
        k = len(list(d.glob("triage-*.md")))
        issue_file, rows_file, verdict_path = d / f"issue-{k}.md", d / f"rows-{k}.md", d / f"triage-{k}.md"
        issue_file.write_text(issue_text(issue, self.authors), encoding="utf-8")
        rows_file.write_text(rows_text(plan, built), encoding="utf-8")
        fixes = root / self.folder / plan_mod.FIX_FILE
        made_fixes = not fixes.is_file()
        if made_fixes:
            fixes.write_text(ISSUES_HEAD.format(stage=self.stage), encoding="utf-8")
        prompt = render("issue_triage", number=str(n), mode=mode, task=task or "-", plan=self.stage,
                        folder=self.folder, issue_file=str(issue_file), rows_file=str(rows_file),
                        verdict=str(verdict_path), fix_max_files=str(self.max_files), date=time.strftime("%Y-%m-%d"))
        before = _snapshot(root)
        old_hashes = {r.id: r.hash for r in [*plan.rows, *plan.fixes] if r.id in built}
        self.journal.decision("Triage", f"#{n}", f"{mode}" + (f" on {task}" if task else ""))
        res = agents.claude(self.cfg, self.run, f"#{n}", "triage", prompt, self.model, d / f"triage-{k}.log",
                            extra_flags=str(self.cfg.get("issues.triage_flags", "")).split())
        self.run.emit("usage", pkg=f"#{n}", agent="claude", model=self.model, step="triage", rc=res.rc,
                      log=str(res.log), **res.usage.as_dict())
        after = _snapshot(root)
        touched = sorted(p for p in before.keys() | after.keys() if before.get(p, "-") != after.get(p, "-"))
        if made_fixes and f"{self.folder}/{plan_mod.FIX_FILE}" not in touched:
            fixes.unlink(missing_ok=True)
        verdict = parse(verdict_path.read_text(encoding="utf-8")) if verdict_path.is_file() else None
        problem = self.check(touched, plan, built, old_hashes, n, verdict)
        if problem:
            _restore(root, touched)
            if made_fixes:
                fixes.unlink(missing_ok=True)
            self.journal.decision("Triage", f"#{n}", f"rejected: {problem} (exit {res.rc}, log {res.log})")
            self.run.emit("result", pkg=f"#{n}", step="triage", ok=False, summary=problem)
            return None
        self.run.emit("result", pkg=f"#{n}", step="triage", ok=True, summary=f"TRIAGE: {verdict['kind']}")
        new = plan_mod.read(self.cfg, self.stage)
        verdict["rows"] = [r.id for r in new.fixes if r.issue == n and r.id not in built]
        if touched:
            changed = plan_mod.changed_rows(root, [p for p in touched if p.endswith(".md")])
            trace = Trace(root / self.folder / "trace.md")
            if f"{self.folder}/trace.md" not in touched:
                for row_id in changed:
                    trace.add(row_id, f"#{n}: {verdict['comment'].splitlines()[0][:300]}", time.strftime("%Y-%m-%d"))
            paths = sorted({*touched, f"{self.folder}/trace.md"} if changed else set(touched))
            sha = gitops.commit_paths(root, f"plan: #{n} triage ({', '.join(changed) or 'notes'})", *paths)
            if self.cfg.get("git.push", True):
                try:
                    gitops.push(root, gitops.branch(root))
                except gitops.GitError as exc:   # the comment must still go out, or the issue is triaged again
                    self.journal.decision("Retry", f"#{n}", f"push failed, the next sync pushes it: {exc}")
            verdict["sha"], verdict["changed"] = sha, changed
            self.journal.decision("Replan", f"#{n}", f"{', '.join(changed) or 'no row'} changed ({sha})")
        self.report(issue, verdict)
        return verdict

    def check(self, touched: list[str], plan: plan_mod.Plan, built: set[str], old_hashes: dict, n: int,
              verdict: dict | None) -> str:
        if verdict is None:
            return "no verdict (line 1 TRIAGE: FIX|PLAN|QUESTION|NOTE, then RELATED, TOUCHES, ---, the comment)"
        outside = [p for p in touched if not p.startswith(self.folder + "/")]
        if outside:
            return f"changed files outside {self.folder}: {', '.join(outside)}"
        if verdict["kind"] in ("QUESTION", "NOTE") and touched:
            return f"{verdict['kind']} must change no file"
        try:
            new = plan_mod.read(self.cfg, self.stage)
        except ValueError as exc:
            return str(exc)
        rows = {r.id: r for r in [*new.rows, *new.fixes]}
        for row_id, digest in old_hashes.items():
            if row_id not in rows:
                return f"removed built row {row_id}"
            if rows[row_id].hash != digest:
                return f"changed built row {row_id}"
        old_fixes = {r.id for r in plan.fixes}
        foreign = [r.id for r in new.fixes if r.id not in old_fixes and r.issue != n]
        if foreign:
            return f"fix rows {', '.join(foreign)} are not of issue #{n}"
        big = [r.id for r in new.fixes if r.id not in old_fixes and len(r.files) > self.max_files]
        if big:
            return f"fix rows {', '.join(big)} list more than {self.max_files} files"
        if verdict["kind"] == "FIX" and not [r for r in new.fixes if r.issue == n and r.id not in built]:
            return "FIX without a fix row of this issue in issues.md"
        return ""

    def report(self, issue: Issue, verdict: dict) -> None:
        n, kind = issue.number, verdict["kind"]
        lines = [verdict["comment"], ""]
        if verdict.get("rows"):
            lines.append(f"Fix rows: {', '.join(verdict['rows'])}; devchain builds them before the next task.")
        if verdict.get("changed"):
            lines.append(f"Plan rows changed ({verdict['sha']}): {', '.join(verdict['changed'])}; the reasons are in "
                         f"`{self.folder}/trace.md`.")
        index = {i.number: i for i in self.tracker.issues()}
        refs = []
        for row_id in verdict["related"]:
            task = next((i for i in index.values() if marker(i.body) and marker(i.body)[1].get("id") == row_id
                         and marker(i.body)[1].get("plan") == self.stage), None)
            refs.append(f"#{task.number} {row_id}" if task else row_id)
            if task and task.number != n and not any(
                    (m := marker(c.body)) and m[0] == "related" and m[1].get("issue") == str(n)
                    for c in task.comments):
                self.tracker.comment(task.number, f"#{n} affects this task: {issue.title}\n\n"
                                                  + mark("related", issue=n))
        if refs:
            lines.append("Related tasks: " + ", ".join(refs))
        held = kind in ("FIX", "QUESTION")
        lines.append(mark("triage", kind=kind, related=verdict["related"], touches=verdict["touches"],
                          rows=verdict.get("rows") or []))
        self.tracker.comment(n, "\n".join(x for x in lines if x is not None))
        label = {"FIX": "in-progress", "QUESTION": "question", "PLAN": "to-verify"}.get(kind)
        drop = tuple(x for x in ("in-progress", "question", "to-verify") if x != label)
        self.tracker.labels(n, add=(label,) if label else (), remove=drop)
        self.journal.decision("Triage", f"#{n}", f"{kind}; related {', '.join(verdict['related']) or '-'}; "
                                                f"{'holds them' if held else 'holds nothing'}")
