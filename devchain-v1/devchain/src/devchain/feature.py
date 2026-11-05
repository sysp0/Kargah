"""Build one task (a plan row or a fix row): Codex implements, the checks run outside the sandbox, a fresh Claude
session reviews. The loop (loop.py) picks the task and reports the outcome; this module only builds.

States of one task: codex -> accept -> build_ui -> tests -> review -> commit -> done.
`Feature.package` returns done | question | stuck | waits | limit | failed; `Feature.info` says more (the question,
the topics it is about, the holder a task waits for, Codex's summary, the commit, the Codex session).
A fix round goes on in the same Codex session (`codex exec resume`). A UI row (title `UI: ...`) first gets a UI spec
from the UI designer; its Playwright spec takes screenshots and the UI review looks at them.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from string import Template

from . import accept, agents, gitops
from . import events as ev
from . import plan as plan_mod
from .config import Config, load
from .events import Run
from .tasks import Trace

PROMPTS = Path(__file__).parent / "prompts"
AGENT_FAILED = "AGENT FAILED: "
FIXED, ANSWER = "PLANFIX: FIXED", "PLANFIX: ANSWER"
CITED = re.compile(r"[\w./-]+\.\w+:\d+")   # path:line, as in spec/decisions.md:95
WAITS_RE = re.compile(r"WAITS FOR:?\s*(#\d+|[PI]\d+[a-z]?)", re.I)
PREFLIGHT = "PRE"   # the row of the plan-wide check in the viewer
ISSUE_ROW = re.compile(r"^I(\d+)[a-z]?$")   # a fix row of <plan folder>/issues.md, written from an issue


def _snapshot(root: Path) -> dict[str, str | None]:
    """Changed paths of the working tree with a content hash (None: deleted), to see what an agent touched."""
    out = {}
    for path in gitops.changed(root):
        f = root / path
        out[path] = hashlib.sha1(f.read_bytes()).hexdigest() if f.is_file() else None
    return out


SCOPE_OK = r"(^|/)tests?/|(^|/)test_[^/]*\.py$|\.spec\.ts$|^docs/progress\.md$|(^|/)__init__\.py$"


def _outside(before: dict, after: dict, folder: str, progress: str) -> list[str]:
    """Paths an agent changed outside the plan folder (the progress file is the agents' own)."""
    touched = [p for p in before.keys() | after.keys() if before.get(p, "-") != after.get(p, "-")]
    return sorted({p for p in touched if not p.startswith(folder + "/") and p != progress})


def _restore(root: Path, paths: list[str]) -> None:
    """Undo an agent's edits of these paths: tracked files back to HEAD, new files deleted."""
    for path in paths:
        if gitops.git(root, "ls-files", "--", path, check=False):
            gitops.git(root, "checkout", "-q", "--", path)
        else:
            (root / path).unlink(missing_ok=True)


def code_hash(root: Path) -> str:
    """devchain's Python code and devchain.toml: a pull during a run changes them, and only a new process loads them
    (the prompts are read on every call)."""
    digest = hashlib.sha1()
    for f in [*sorted(Path(__file__).parent.rglob("*.py")), root / "devchain.toml"]:
        if f.is_file():
            digest.update(f.read_bytes())
    return digest.hexdigest()


def last_line(log: Path | None) -> str:
    """The last non-empty line of an agent log, for a one-line reason."""
    if not log or not log.is_file():
        return "no log"
    lines = [line.strip() for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-1][:200] if lines else "empty log"


def render(name: str, **values) -> str:
    rules = (PROMPTS / "rules.md").read_text(encoding="utf-8").strip()
    return Template((PROMPTS / f"{name}.md").read_text(encoding="utf-8")).safe_substitute(rules=rules, **values)


def earlier_round(d: Path, round_: int) -> str:
    """The last round's findings and Codex's answer to them, so a review does not ask again for an edit that Codex
    showed a check needs."""
    findings, answer = d / f"findings-{round_ - 1}.md", d / f"codex-{round_}" / "last-message.txt"
    if not findings.is_file():
        return "This is the first review of this package."
    text = ["The last round's findings:", findings.read_text(encoding="utf-8")[:4000]]
    if answer.is_file():
        text += ["Codex's answer to them:", answer.read_text(encoding="utf-8", errors="replace")[:3000]]
    return "\n".join(text)


def plan_folder(cfg: Config, stage: str) -> dict[str, str] | None:
    """{package: part file} of the plan folder, in run order; None when <stage> is not a plan folder."""
    found = plan_mod.read(cfg, stage)
    if found is None:
        return None
    return {r.id: f"{found.folder}/{r.part}" for r in found.rows}


def row_titles(part: Path) -> dict[str, str]:
    return {r.id: r.title for r in plan_mod.table(part)[0]}


def plan_branch_name(cfg: Config, stage: str) -> str:
    """One branch per plan: plan/<plan folder>."""
    return f"{cfg.get('git.plan_branch_prefix', 'plan/')}{stage}"


def pr_link(cfg: Config, name: str) -> str | None:
    repo = cfg.get("git.github_repo")
    return f"https://github.com/{repo}/pull/new/{name}" if repo else gitops.pr_url(cfg.root, name)


def questions(note: str) -> str:
    """The "Questions for the owner" section of a plan-problem note, else the whole note."""
    m = re.search(r"^##+\s*Questions for the owner\s*$(.*)", note, re.M | re.S)
    return (m.group(1) if m else note).strip()


class Feature:
    def __init__(self, cfg: Config, run: Run, stage: str):
        self.cfg, self.run, self.stage = cfg, run, stage
        self.folder = plan_mod.folder_of(cfg, stage)
        self.max_rounds = int(cfg.get("loop.max_fix_rounds", 3))
        self.review_model = cfg.get("models.review", "claude-sonnet-5-5")
        self.ui_model = cfg.get("ui.model", self.review_model)   # the UI designer and the UI review
        self.stack_up: tuple[str, int] | None = None   # (row, round) whose QA services already run this tree
        self.planfix_model = cfg.get("planfix.model", "")   # empty: a plan problem always goes to the owner
        self.planfix_max = int(cfg.get("planfix.max_per_run", 80))
        self.planfix_pkg_max = int(cfg.get("planfix.max_per_package", 5))
        self.resume_rounds = bool(cfg.get("codex.resume_rounds", True))
        self.specs: dict[str, str] = {}        # fix row -> its issue's Playwright spec, run by the checks
        self.reproduced: dict[str, str] = {}   # fix row -> hash of its spec that failed before the fix
        self.holders = ""                      # open questions and issues, for Codex's WAITS FOR
        self.info: dict = {}
        self.plan = plan_mod.read(cfg, stage)

    def reload(self) -> None:
        self.plan = plan_mod.read(self.cfg, self.stage)

    def row(self, pkg: str):
        return self.plan.get(pkg) if self.plan else None

    def strays(self, pkg: str) -> list[str]:
        """Changed paths the row did not list: not in its `files`, not a test, not in the plan folder. Everything
        changed is committed, so this is checked before the review."""
        row = self.row(pkg)
        if not row or not row.files:
            return []
        ok = re.compile(self.cfg.get("feature.scope_ok", SCOPE_OK))
        listed = [f.rstrip("/") for f in row.files]
        return [p for p in gitops.changed(self.cfg.root)
                if not (any(p == f or p.startswith(f + "/") for f in listed) or ok.search(p)
                        or p.startswith(self.folder + "/"))]

    def plan_of(self, pkg: str) -> str:
        return self.plan.path_of(pkg) if self.plan else f"{self.folder}/{plan_mod.FIX_FILE}"

    def note_of(self, pkg: str) -> str:
        """Where Codex or the review explains a plan problem that stopped the package."""
        return f"{self.folder}/blocked-{pkg}.md"

    # ---- UI rows ------------------------------------------------------------------------------------------------
    def is_ui(self, pkg: str) -> bool:
        row = self.row(pkg)
        return bool(row and row.ui)

    def ui_spec_of(self, pkg: str) -> str:
        return f"{self.folder}/ui-{pkg}.md"

    def shots_spec_of(self, pkg: str) -> str:
        """The UI row's Playwright spec: it reaches each state of the UI spec and saves a screenshot."""
        return f"{self.cfg.get('qa.dir', 'qa')}/tests/ui/{self.stage}-{pkg.lower()}.spec.ts"

    def ui_values(self, pkg: str) -> dict[str, str]:
        return {"ui_spec": self.ui_spec_of(pkg), "shots_spec": self.shots_spec_of(pkg),
                "design": self.cfg.get("ui.design_system", "docs/ui/design-system.md"),
                "skill": self.cfg.get("ui.skill", ".claude/skills/ui-ux-pro-max")}

    def ui_ready(self, pkg: str, answer: str = "") -> str | None:
        """None when the UI row has a finished UI spec (the designer writes it when it is missing); else the
        designer's open questions. An answer of the owner makes the designer write the spec again."""
        root, spec = self.cfg.root, self.ui_spec_of(pkg)
        if answer and (root / spec).is_file() and not (root / spec).read_text(encoding="utf-8").rstrip().endswith(
                "UI SPEC: WRITTEN"):
            (root / spec).unlink()
        if not (root / spec).is_file():
            d = self.run.pkg_dir(pkg)
            before = _snapshot(root)
            self.state(pkg, "ui_design", 0, message=f"the UI designer writes {spec}")
            prompt = render("ui_design", package=pkg, plan=self.plan_of(pkg), **self.ui_values(pkg))
            if answer:
                prompt += f"\n\nThe owner answered your earlier open questions:\n{answer}"
            res = agents.claude(self.cfg, self.run, pkg, "ui_design", prompt, self.ui_model, d / "ui-design.log")
            self.usage(pkg, "claude", self.ui_model, res, "ui_design")
            others = [p for p in _outside(before, _snapshot(root), "-", "-") if p != spec]
            if others:
                _restore(root, others)   # the designer writes only the UI spec
                self.run.emit("note", pkg=pkg, text=f"ui design: undid changes outside the spec: {', '.join(others)}")
            if not (root / spec).is_file():
                return f"The UI designer wrote no {spec} (exit {res.rc}): {last_line(res.log)}"
        text = (root / spec).read_text(encoding="utf-8")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        last = lines[-1] if lines else ""
        self.run.emit("result", pkg=pkg, step="ui_design", round=0, ok=last == "UI SPEC: WRITTEN", summary=last)
        if last == "UI SPEC: WRITTEN":
            return None
        m = re.search(r"^##\s*Open questions\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        return (m.group(1).strip() if m else text[-2000:]) or f"{spec} does not end with 'UI SPEC: WRITTEN'"

    # ---- events -----------------------------------------------------------------------------------------------
    def state(self, pkg: str, state: str, round_: int | None = None, **extra) -> None:
        self.run.emit("pkg", pkg=pkg, state=state, round=round_, **extra)

    def usage(self, pkg: str, agent: str, model: str | None, result: agents.Result, step: str = "") -> None:
        self.run.emit("usage", pkg=pkg, agent=agent, model=model, step=step or agent, rc=result.rc,
                      log=str(result.log or ""), **result.usage.as_dict())

    # ---- the Blocked: line ---------------------------------------------------------------------------------------
    def progress_path(self) -> Path:
        return self.cfg.root / self.cfg.get("paths.progress", "docs/progress.md")

    def blocked(self) -> str | None:
        progress = self.progress_path()
        if not progress.is_file():
            return None
        for line in progress.read_text(encoding="utf-8").splitlines():
            if line.startswith("Blocked:") and not re.match(r"^Blocked:\s*none\s*$", line, re.I):
                return line.removeprefix("Blocked:").strip()
        return None

    def set_blocked(self, reason: str) -> None:
        progress = self.progress_path()
        if progress.is_file():
            text = re.sub(r"^Blocked:.*$", f"Blocked: {reason}", progress.read_text(encoding="utf-8"), flags=re.M)
            progress.write_text(text, encoding="utf-8")

    def clear_blocked(self) -> None:
        self.set_blocked("none")

    def work_in_tree(self, note: str) -> bool:
        """True when the tree holds package work, not only the stop bookkeeping (progress line, plan note)."""
        bookkeeping = {self.cfg.get("paths.progress", "docs/progress.md"), note}
        return any(path not in bookkeeping for path in gitops.changed(self.cfg.root))

    # ---- plan problems ---------------------------------------------------------------------------------------------
    def planfix_used(self, pkg: str | None = None) -> int:
        """Plan checks of this run so far (of one package when pkg is given), read from its event log."""
        events, _ = ev.read(self.run.events_path)
        return sum(1 for e in events if e.get("type") == "result" and e.get("step") in ("planfix", "preflight_fix")
                   and (pkg is None or e.get("pkg") == pkg))

    def ask_owner(self, pkg: str, round_: int, reason: str) -> str:
        """The owner decides: the note's questions (or the reason) go to the task issue; the work stays as WIP."""
        note = self.cfg.root / self.note_of(pkg)
        text = note.read_text(encoding="utf-8", errors="replace") if note.is_file() else ""
        self.info["question"] = questions(text) if text.strip() else reason
        self.info["message"] = reason
        self.state(pkg, "blocked", round_, message=reason)
        return "question"

    def on_blocked(self, pkg: str, round_: int, reason: str) -> str:
        """`WAITS FOR:` holds the task; any other plan problem goes to the plan check first, and to the owner only
        when spec/ has no answer."""
        m = WAITS_RE.search(reason)
        if m:
            self.info["target"] = m.group(1).upper()
            self.info["message"] = reason
            self.state(pkg, "blocked", round_, message=reason)
            return "waits"
        if not self.planfix_model:
            return self.ask_owner(pkg, round_, reason)
        if self.planfix_used() >= self.planfix_max:
            return self.ask_owner(pkg, round_, f"{reason}; the {self.planfix_max} plan checks of this run are used")
        if self.planfix_used(pkg) >= self.planfix_pkg_max:
            return self.ask_owner(pkg, round_, f"{reason}; the {self.planfix_pkg_max} plan checks of {pkg} are used")
        problem, answer = self.plan_fix(pkg, self.planfix_used() + 1)
        if problem:
            return self.ask_owner(pkg, round_, f"{reason}; plan check: {problem}")
        return self.package(pkg, resume=True, session=self.info.get("session", ""),
                            context="The plan check read spec/, the plan and the code and answered your stop; follow "
                                    "it and continue. The work already in the tree stays.\n" + answer)

    def on_stuck(self, pkg: str, round_: int, d: Path) -> str:
        """The fix rounds are used and the checks still fail: the plan check reads every round's findings once and
        Codex gets fresh rounds with its answer; otherwise the task is stuck and the owner helps."""
        reason = f"still failing after {self.max_rounds} fix rounds"
        note = self.cfg.root / self.note_of(pkg)
        rounds = sorted(d.glob("findings-*.md"), key=lambda f: int(f.stem.split("-")[1]))
        text = [f"# {pkg} is stuck: the checks still fail after {self.max_rounds} fix rounds",
                "", "Codex's work is in the tree (git diff). The findings of each round, oldest first:"]
        for f in rounds[-4:]:
            text += ["", f"## Round {f.stem.split('-')[1]}", f.read_text(encoding="utf-8", errors="replace")[-3000:]]
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("\n".join(text) + "\n", encoding="utf-8")
        last = rounds[-1].read_text(encoding="utf-8", errors="replace")[-3000:] if rounds else reason
        if self.info.get("stuck_checked") or not self.planfix_model:
            self.info.update(question=last, message=reason)
            self.state(pkg, "blocked", round_, message=reason)
            return "stuck"
        self.info["stuck_checked"] = True
        outcome = self.on_blocked(pkg, round_, reason)
        if outcome == "question":
            self.info["question"] = last
            return "stuck"
        return outcome

    def plan_fix(self, pkg: str, n: int) -> tuple[str | None, str]:
        """(None, answer) when the plan check fixed the row or answered from spec/; else (why the owner decides, "")."""
        root, note = self.cfg.root, self.note_of(pkg)
        folder = self.folder
        d = self.run.pkg_dir(pkg)
        verdict_path = d / f"planfix-{n}.md"
        verdict_path.unlink(missing_ok=True)
        before = _snapshot(root)
        self.state(pkg, "planfix", n, message="checking the plan problem against spec/ and the code")
        prompt = render("planfix", package=pkg, plan=self.plan_of(pkg), note=note, folder=folder,
                        verdict=str(verdict_path))
        flags = str(self.cfg.get("planfix.flags", "")).split()
        res = agents.claude(self.cfg, self.run, pkg, "planfix", prompt, self.planfix_model,
                            d / f"planfix-{n}.log", extra_flags=flags)
        self.usage(pkg, "claude", self.planfix_model, res, "planfix")
        verdict = verdict_path.read_text(encoding="utf-8") if verdict_path.is_file() else ""
        lines = verdict.strip().splitlines()
        first = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip()
        about = re.search(r"^ABOUT:\s*(.+)$", verdict, re.M)
        if about:
            self.info["about"] = [t.strip(" `") for t in re.split(r"[,;]", about.group(1)) if t.strip(" `")]
        self.run.emit("result", pkg=pkg, step="planfix", round=n, ok=first in (FIXED, ANSWER),
                      summary=first or "no verdict written")
        after = _snapshot(root)
        touched = [p for p in before.keys() | after.keys() if before.get(p, "-") != after.get(p, "-")]
        outside = _outside(before, after, folder, self.cfg.get("paths.progress", "docs/progress.md"))
        if outside:
            _restore(root, outside)
            return f"it changed files outside {folder}: {', '.join(outside)}", ""
        if first not in (FIXED, ANSWER):
            if first == "PLANFIX: ASK":
                return "questions for the owner", ""
            if not res.ok or not res.usage.output:
                return f"plan check agent failed (exit {res.rc}): {last_line(res.log)}", ""
            return "no verdict written", ""
        plan_paths = sorted(p for p in touched if p.startswith(folder + "/") and p != note)
        if first == FIXED and not plan_paths:
            return "it said FIXED but changed no plan file", ""
        if first == ANSWER and not body:
            return "it said ANSWER but wrote no answer", ""
        if not CITED.search(body):  # an answer that cites no spec/, plan or code line may be the model's own logic
            _restore(root, plan_paths)  # its row edits are not kept either
            return "it cited no spec/, plan or code line (path:line) for its answer", ""
        (root / note).unlink(missing_ok=True)
        self.clear_blocked()
        if plan_paths:
            changed = self.changed_rows(plan_paths) or [pkg]
            trace = Trace(root / folder / "trace.md")
            for row_id in changed:
                trace.add(row_id, f"plan check while building {pkg}: {body.splitlines()[0] if body else first}",
                          time.strftime("%Y-%m-%d"))
            commit = gitops.commit_paths(root, f"plan: {', '.join(changed)} fixed by the plan check of {pkg}",
                                         *sorted({*plan_paths, f"{folder}/trace.md"}))
            if self.cfg.get("git.push", True):
                gitops.push(root, gitops.branch(root))
            self.reload()
            self.run.emit("note", pkg=pkg, text=f"plan check ({commit}): {' '.join(body.split())[:400]}")
        else:
            self.run.emit("note", pkg=pkg, text=f"plan check: {' '.join(body.split())[:400]}")
        return None, body

    def changed_rows(self, paths: list[str]) -> list[str]:
        return plan_mod.changed_rows(self.cfg.root, paths)

    # ---- once per plan -------------------------------------------------------------------------------------------
    def preflight(self) -> str:
        """Once per plan: Codex checks every row against the code, the plan check fixes what spec/ answers. Returns
        done, failed, or blocked with self.info["question"]. Only an explicitly clean report releases the loop."""
        root, pkg, folder = self.cfg.root, PREFLIGHT, self.folder
        out = f"{folder}/preflight.md"
        self.info = {}
        if (root / out).is_file():
            text = (root / out).read_text(encoding="utf-8")
            if text.splitlines()[:1] == ["PREFLIGHT: CLEAN"]:
                return "done"
            self.info = {"question": text[-3000:], "message": "unresolved preflight: " + out}
            self.state(pkg, "blocked", 0, message=self.info["message"])
            return "blocked"
        d = self.run.pkg_dir(pkg)
        before = _snapshot(root)
        self.state(pkg, "codex", 0, message="checking every row of the plan against the code")
        res = agents.codex(self.cfg, self.run, pkg, "codex", render("preflight", folder=folder, out=out),
                           d / "codex-0")
        self.usage(pkg, "codex", self.cfg.get("models.codex"), res, "codex")
        text = (root / out).read_text(encoding="utf-8") if (root / out).is_file() else ""
        first = text.splitlines()[0].strip() if text.strip() else ""
        self.run.emit("result", pkg=pkg, step="preflight", round=0, ok=first == "PREFLIGHT: CLEAN",
                      summary=first or "no preflight file written")
        outside = _outside(before, _snapshot(root), folder, self.cfg.get("paths.progress", "docs/progress.md"))
        if outside:
            _restore(root, outside)
        if not res.ok or first not in ("PREFLIGHT: CLEAN", "PREFLIGHT: PROBLEMS"):
            _restore(root, gitops.changed(root))
            self.info["message"] = f"preflight: codex exit {res.rc}, {first or 'no file written'}"
            self.state(pkg, "failed", 0, message=self.info["message"])
            return "failed"
        reason = ""
        if first == "PREFLIGHT: PROBLEMS":
            if not self.planfix_model:
                reason = "preflight found plan problems; no plan check is configured"
            else:
                verdict_path = d / "preflight-fix.md"
                before = _snapshot(root)
                self.state(pkg, "planfix", 0, message="fixing the rows the preflight found")
                prompt = render("preflight_fix", folder=folder, out=out, verdict=str(verdict_path))
                res = agents.claude(self.cfg, self.run, pkg, "planfix", prompt, self.planfix_model,
                                    d / "preflight-fix.log", extra_flags=str(self.cfg.get("planfix.flags", "")).split())
                self.usage(pkg, "claude", self.planfix_model, res, "planfix")
                verdict = verdict_path.read_text(encoding="utf-8") if verdict_path.is_file() else ""
                vfirst = verdict.splitlines()[0].strip() if verdict.strip() else ""
                self.run.emit("result", pkg=pkg, step="preflight_fix", round=0, ok=vfirst == FIXED,
                              summary=vfirst or "no verdict written")
                outside = _outside(before, _snapshot(root), folder, self.cfg.get("paths.progress", "docs/progress.md"))
                if outside:
                    _restore(root, outside)
                if vfirst != FIXED:
                    reason = "questions for the owner in " + out if vfirst == "PLANFIX: ASK" else \
                        "the plan check wrote no verdict"
        report = root / out
        lines = report.read_text(encoding="utf-8").splitlines()
        lines[0] = "PREFLIGHT: BLOCKED" if reason else "PREFLIGHT: CLEAN"
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths = [p for p in gitops.changed(root) if p.startswith(folder + "/")]
        changed = self.changed_rows([p for p in paths if gitops.git(root, "ls-files", "--", p, check=False)])
        if changed:
            trace = Trace(root / folder / "trace.md")
            for row_id in changed:
                trace.add(row_id, "preflight: the row did not match the code (see preflight.md)",
                          time.strftime("%Y-%m-%d"))
            paths = sorted({*paths, f"{folder}/trace.md"})
        commit = gitops.commit_paths(root, "plan: preflight check of every row", *paths)
        if self.cfg.get("git.push", True):
            gitops.push(root, gitops.branch(root))
        self.reload()
        if reason:
            self.info["question"] = (root / out).read_text(encoding="utf-8", errors="replace")[-3000:]
            self.info["message"] = reason
            self.state(pkg, "blocked", 0, message=reason, commit=commit)
            return "blocked"
        self.state(pkg, "done", 0, commit=commit, message="plan checked against the code")
        return "done"

    # ---- fix rows: the issue's scenario must fail first --------------------------------------------------------------
    def spec_of(self, pkg: str) -> str:
        return f"{self.cfg.get('qa.dir', 'qa')}/tests/issues/issue-{ISSUE_ROW.match(pkg).group(1)}.spec.ts"

    def reproduce(self, row: str) -> str | None:
        """Before the fix: Codex writes only the issue's Playwright spec and the tool runs it on the current code. It
        must fail. None when it does (the spec stays for the fix); "limit" at a usage limit; else what to tell the
        reporter."""
        from .qa import QA

        root, spec = self.cfg.root, self.spec_of(row)
        self.specs[row] = spec
        d = self.run.pkg_dir(row)
        self.state(row, "reproduce", 0, message="Codex writes the issue's spec; it must fail on the current code")
        seed = self.seed_env(row)["QA_SEED"]
        res = agents.codex(self.cfg, self.run, row, "codex",
                           render("issue_reproduce", package=row, plan=self.plan_of(row), spec=spec, seed=seed),
                           d / "reproduce")
        self.usage(row, "codex", self.cfg.get("models.codex"), res, "reproduce")
        others = [p for p in gitops.changed(root) if p != spec]
        if others:
            _restore(root, others)   # only the spec may change in this step
            self.run.emit("note", pkg=row, text=f"reproduce: undid changes outside the spec: {', '.join(others)}")
        if res.rc == 75:
            _restore(root, [spec])
            return "limit"
        if not res.ok or spec not in gitops.changed(root):
            _restore(root, [spec])
            self.state(row, "failed", 0, message="Codex wrote no spec for the issue")
            return f"devchain could not write a test for row `{row}` from the scenario (codex exit {res.rc}). " \
                   "Make the scenario's steps and expected values exact in a comment."
        qa = QA(self.cfg, self.run, "issues", [], env=self.seed_env(row))
        up = qa.ensure_services(f"{row}-reproduce")
        if up is not None and not up.ok:
            _restore(root, [spec])
            self.state(row, "failed", 0, message="QA services did not start")
            return "devchain could not start the QA stack to reproduce this issue.\n\n" + up.text[-1500:]
        ok, output, _ = qa.playwright(Path(spec).name.removesuffix(".spec.ts"), f"{row}-reproduce")
        tail = "\n".join(output.splitlines()[-15:])
        self.run.emit("result", pkg=row, step="reproduce", round=0, ok=not ok,
                      summary="the spec fails on the current code: reproduced" if not ok else
                      "the spec passes: not reproduced")
        if ok:
            _restore(root, [spec])
            self.state(row, "blocked", 0, message="not reproduced: the spec passes on the current code")
            return (f"devchain wrote a test from the scenario (row `{row}`) and it **passes** on the current code, so "
                    "the problem did not show with these steps. Make the steps, the data and the expected values exact "
                    f"(with numbers) in a comment.\n\n```\n{tail}\n```")
        self.reproduced[row] = hashlib.sha1((root / spec).read_bytes()).hexdigest()
        return None

    def seed_env(self, row: str) -> dict:
        """The QA data set an issue was found on (its row's seed column)."""
        found = self.row(row)
        seed = (found.cells.get("seed") if found else "") or str((self.cfg.get("qa.seeds") or ["shop"])[0])
        return {"QA_SEED": seed, "QA_TENANT": seed}

    # ---- one task --------------------------------------------------------------------------------------------------
    def package(self, pkg: str, resume: bool = False, session: str = "", context: str = "") -> str:
        """Build one task. resume: the task's work is in the tree (kept from a stop). session: go on in that Codex
        session with context as the message; without a session, context is added to the task prompt."""
        keep = self.info.get("stuck_checked") if self.info.get("pkg") == pkg else None
        self.info = {"pkg": pkg, **({"stuck_checked": True} if keep else {})}
        d = self.run.pkg_dir(pkg)
        note = self.note_of(pkg)
        ui = self.is_ui(pkg)
        if ISSUE_ROW.match(pkg) and (self.cfg.root / self.spec_of(pkg)).is_file():
            self.specs[pkg] = self.spec_of(pkg)
        if ui:
            why = self.ui_ready(pkg, answer=context if resume else "")
            if why:
                if why.startswith("The UI designer wrote no"):
                    return self.fail(pkg, 0, why)
                self.info["question"] = why
                self.info["message"] = f"the UI designer has open questions in {self.ui_spec_of(pkg)}"
                self.state(pkg, "blocked", 0, message=self.info["message"])
                return "question"
        prompt = render("task_ui" if ui else "task", package=pkg, plan=self.plan_of(pkg), note=note,
                        holders=self.holders or "none", **(self.ui_values(pkg) if ui else {}))
        if pkg in self.reproduced:
            prompt += (f"\n\nThe test of this row is already in the tree: {self.specs[pkg]} reproduces the problem "
                       "(it fails on the current code). Do not change it; make it pass with the change the row "
                       "describes. The tool runs it in the browser after your change.")
        if context and not session:
            prompt += "\n\n" + context
        work = False
        for round_ in range(self.max_rounds + 1):
            first_resumed = round_ == 0 and bool(session)
            message = context if first_resumed else prompt
            (d / f"prompt-{round_}.txt").write_text(message, encoding="utf-8")
            if resume and round_ == 0:
                work = self.work_in_tree(note)
                self.clear_blocked()
                (self.cfg.root / note).unlink(missing_ok=True)
            if resume and round_ == 0 and work and not context:
                self.state(pkg, "resume", round_, message="checking the work already in the tree")
            else:
                self.state(pkg, "codex", round_)
                use = session if (first_resumed or (round_ > 0 and self.resume_rounds)) else ""
                res = agents.codex(self.cfg, self.run, pkg, "codex", message, d / f"codex-{round_}", session=use)
                self.usage(pkg, "codex", self.cfg.get("models.codex"), res, "codex")
                session = res.session or session
                self.info["session"] = session
                self.info["summary"] = res.text.strip()[-3000:]
                if res.rc == 75:
                    self.info["message"] = "still at the usage limit"
                    return "limit"
                if not res.ok:
                    return self.fail(pkg, round_, f"codex exit {res.rc}: {last_line(res.log)}")
                reason = self.blocked()
                if reason:
                    return self.on_blocked(pkg, round_, reason)
            if gitops.is_clean(self.cfg.root):
                return self.fail(pkg, round_, "Codex changed nothing")
            findings = self.check(pkg, round_, d)
            if findings is None:
                return "done"
            if findings.startswith(AGENT_FAILED):
                return self.fail(pkg, round_, findings.removeprefix(AGENT_FAILED))
            if findings.startswith("VERDICT: PLAN"):
                reason = f"plan problem, see {note}"
                self.set_blocked(reason)
                return self.on_blocked(pkg, round_, reason)
            (d / f"findings-{round_}.md").write_text(findings, encoding="utf-8")
            self.run.emit("findings", pkg=pkg, round=round_, text=findings[:4000])
            if round_ >= self.max_rounds:
                return self.on_stuck(pkg, round_, d)
            prompt = render("fix", package=pkg, plan=self.plan_of(pkg), findings=findings, note=note)
            if ui:
                prompt += "\n" + render("fix_ui", **self.ui_values(pkg))
        return self.fail(pkg, self.max_rounds, "no round left")

    def fail(self, pkg: str, round_: int, message: str) -> str:
        self.info["message"] = message
        self.state(pkg, "failed", round_, message=message)
        return "failed"

    def check(self, pkg: str, round_: int, d: Path) -> str | None:
        """None when the package is committed; otherwise the findings for the next Codex round."""
        root = self.cfg.root
        problems = []  # every gate runs, so one Codex round sees every failure instead of one per round
        self.state(pkg, "accept", round_)
        out = accept.run(self.cfg, self.run, pkg, d, str(round_))
        self.run.emit("result", pkg=pkg, step="accept", round=round_, ok=out.ok, summary=out.summary)
        if not out.ok:
            problems.append(f"Acceptance check failed ({out.summary}):\n{out.tail}")

        ui_dir = self.cfg.get("ui.dir")
        ui_built = True
        if ui_dir and any(p.startswith(ui_dir.rstrip("/") + "/") for p in gitops.changed(root)):
            self.state(pkg, "build_ui", round_)
            res = agents.shell(self.cfg, self.run, pkg, "build_ui", self.cfg.get("ui.build", "npm run build"),
                               d / f"ui-build-{round_}.log")
            self.run.emit("result", pkg=pkg, step="build_ui", round=round_, ok=res.ok,
                          summary="UI build ok" if res.ok else "UI build failed")
            ui_built = res.ok
            if not res.ok:
                problems.append(f"UI build failed:\n{res.text}")
            else:   # the build never renders a page: the smoke specs open them in the browser
                for smoke in self.cfg.get("ui.smoke") or []:
                    if (root / smoke).is_file():
                        found = self.issue_spec(pkg, round_, smoke)
                        if found and found[0].startswith(AGENT_FAILED):
                            return found[0]
                        problems += found
        shots: list[Path] = []
        if self.is_ui(pkg) and ui_built:   # the UI row's spec reaches each state of the UI spec and screenshots it
            spec = self.shots_spec_of(pkg)
            if not (root / spec).is_file():
                problems.append(f"Write {spec}: one test per item of the UI spec's Capture list, each saving a "
                                "screenshot with test.info().outputPath.")
            else:
                found = self.issue_spec(pkg, round_, spec, shots)
                if found and found[0].startswith(AGENT_FAILED):
                    return found[0]
                problems += found
                if not found and not any(p.suffix == ".png" for p in shots):
                    problems.append(f"{spec} passed but saved no screenshot: each test ends with page.screenshot("
                                    "{ path: test.info().outputPath(\"<nn>-<state>.png\"), fullPage: true }).")

        test_cmd = self.cfg.get("loop.test_cmd")
        if "devchain.toml" in gitops.changed(root):
            test_cmd = load(root).get("loop.test_cmd")
        if test_cmd:
            self.state(pkg, "tests", round_)
            res = agents.shell(self.cfg, self.run, pkg, "tests", test_cmd, d / f"tests-{round_}.log")
            last = res.text.splitlines()[-1] if res.text else ""
            self.run.emit("result", pkg=pkg, step="tests", round=round_, ok=res.ok, summary=last)
            if not res.ok:
                log = (d / f"tests-{round_}.log").read_text(encoding="utf-8", errors="replace").splitlines()
                hits = [line for line in log if re.search(r"FAILED|Error|assert", line)][:30]
                problems.append("Fast tests failed:\n" + "\n".join(hits or log[-30:]))
        spec = self.specs.get(pkg)
        if pkg in self.reproduced and (not (root / spec).is_file() or hashlib.sha1(
                (root / spec).read_bytes()).hexdigest() != self.reproduced[pkg]):
            problems.append(f"{spec} reproduced the problem before the fix and must stay as it was; undo your edit of "
                            "it and fix the app code instead.")
        elif spec and (root / spec).is_file():  # an issue's scenario: its spec must pass in the browser
            found = self.issue_spec(pkg, round_, spec)
            if found and found[0].startswith(AGENT_FAILED):
                return found[0]
            problems += found
        strays = self.strays(pkg)
        if strays:
            problems.append("Files outside the row (its `files` column, tests, the plan folder): "
                            + ", ".join(strays) + ". Revert them; if the row truly needs them, stop with a plan "
                            "problem that names each file and why.")
        if problems:
            return "\n\n".join(f"{i}. {text}" for i, text in enumerate(problems, 1))

        self.state(pkg, "review", round_)
        verdict_path = d / f"verdict-{round_}.md"
        verdict_path.unlink(missing_ok=True)
        if self.is_ui(pkg):   # the UI review looks at the screenshots against the UI spec and the design system
            model = self.ui_model
            prompt = render("review_ui", package=pkg, plan=self.plan_of(pkg), verdict=str(verdict_path),
                            note=self.note_of(pkg), earlier=earlier_round(d, round_), **self.ui_values(pkg),
                            shots="\n".join(f"- {p}" for p in sorted(shots) if p.suffix == ".png"))
        else:
            model = self.review_model
            prompt = render("review", package=pkg, plan=self.plan_of(pkg), verdict=str(verdict_path),
                            note=self.note_of(pkg), earlier=earlier_round(d, round_))
        res = agents.claude(self.cfg, self.run, pkg, "review", prompt, model, d / f"review-{round_}.log")
        self.usage(pkg, "claude", model, res, "review")
        verdict = verdict_path.read_text(encoding="utf-8") if verdict_path.is_file() else ""
        if res.rc == 75:
            return f"{AGENT_FAILED}review still at the usage limit"
        if not verdict.strip() and (not res.ok or not res.usage.output):
            # nothing a Codex round can fix (a login expired, the CLI is missing): stop instead of burning rounds
            return f"{AGENT_FAILED}review agent failed (exit {res.rc}, no output): {last_line(res.log)}"
        first = verdict.splitlines()[0].strip() if verdict.strip() else ""
        self.run.emit("result", pkg=pkg, step="review", round=round_, ok=first == "VERDICT: PASS",
                      summary=first or "no verdict written")
        if first == "VERDICT: PLAN":
            return verdict
        if first != "VERDICT: PASS":
            if not verdict.strip():
                return "1. The review wrote no verdict; re-check the package acceptance."
            return "\n".join(line for line in verdict.splitlines() if not re.match(r"^(VERDICT|COMMIT):", line))

        message = next((line.removeprefix("COMMIT:").strip() for line in verdict.splitlines()
                        if line.startswith("COMMIT:")), "") or f"feat: package {pkg}"
        if m := ISSUE_ROW.match(pkg):
            message = f"{message} (#{m.group(1)})"   # GitHub links the commit to the issue
        row = self.row(pkg)
        trailers = [f"Package: {pkg}"]   # the loop reads which tasks are built from these
        if row:
            trailers.append(f"Part: {row.part}")
            if row.touches:
                trailers.append(f"Touches: {', '.join(sorted(row.touches))}")
        message = f"{message}\n\n" + "\n".join(trailers)
        self.state(pkg, "commit", round_)
        sha = gitops.commit_all(root, message)
        name = gitops.branch(root)
        pushed = False
        if self.cfg.get("git.push", True):
            gitops.push(root, name)
            pushed = True
        self.info.update(sha=sha, branch=name, title=message.splitlines()[0])
        self.state(pkg, "done", round_, commit=sha, branch=name, pushed=pushed, message=message,
                   pr=pr_link(self.cfg, name) if pushed else None)
        return None

    def issue_spec(self, pkg: str, round_: int, spec: str, kept: list[Path] | None = None) -> list[str]:
        """Restart the QA services with this tree's code (once per round), then run the Playwright spec
        qa/tests/<suite>/<name>. kept gets the files it left (screenshots, error context)."""
        from .qa import QA

        qa = QA(self.cfg, self.run, Path(spec).parent.name, [], env=self.seed_env(pkg))
        qa.services_up = self.stack_up == (pkg, round_)
        self.state(pkg, "playwright", round_)
        up = qa.ensure_services(f"{pkg}-{round_}")
        if up is not None and not up.ok:
            return [AGENT_FAILED + "QA services did not start:\n" + up.text[-1500:]]
        self.stack_up = (pkg, round_)
        ok, output, files = qa.playwright(Path(spec).name.removesuffix(".spec.ts"), f"{pkg}-{round_}")
        if kept is not None:
            kept += files
        self.run.emit("result", pkg=pkg, step="playwright", round=round_, ok=ok,
                      summary=(output.splitlines() or [""])[-1][:200])
        return [] if ok else [f"Playwright spec {spec} failed:\n{output[-2000:]}"]
