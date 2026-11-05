"""QA: Codex writes one Playwright spec per scenario, the tool runs it outside the sandbox, Claude triages.

Per scenario: codex (spec only) -> playwright -> review (pass) | triage (fail).
Triage tags each failure [TEST] (the spec is wrong: back to Codex), [APP] (the app is wrong: devchain files an issue
labelled qa in the feedback form's format, and the loop's triage plans the fix) or [ENV] (the QA stack is wrong:
the run stops). QA never fixes the app itself and never stops the loop (M05). The loop runs it in its own worktree
and stack when every task of a part is built (qaloop.py); ./dev qa runs it in this tree.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import agents, forge, gitops
from .config import Config
from .events import Run
from .feature import render

SCENARIO_RE = re.compile(r"^##\s+(S\d+[a-z]?)\b(.*)$")


def scenarios_in(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [m.group(1) for line in path.read_text(encoding="utf-8").splitlines() if (m := SCENARIO_RE.match(line))]


class QA:
    def __init__(self, cfg: Config, run: Run, suite: str, scenarios: list[str],
                 env: dict | None = None, commit: bool = True, plan: str = "", part: str = ""):
        self.cfg, self.run, self.suite = cfg, run, suite
        self.env = {**(cfg.get("qa.env") or {}), **(env or {})}
        if self.env.get("QA_UI_PORT"):
            self.env.setdefault("QA_UI_URL", f"http://localhost:{self.env['QA_UI_PORT']}")
        self.commit_specs = commit   # False in the loop's QA worktree: the loop copies the green specs
        self.plan, self.part = plan, part
        self.suite_rel = f"{cfg.get('qa.scenarios_dir', 'docs/qa')}/{suite}.md"
        self.suite_path = cfg.root / self.suite_rel
        self.scenarios = scenarios or scenarios_in(self.suite_path)
        self.max_rounds = int(cfg.get("loop.max_fix_rounds", 3))
        self.model = cfg.get("qa.triage_model") or cfg.get("models.review", "claude-sonnet-5-5")
        self.qa_dir = cfg.root / cfg.get("qa.dir", "qa")
        self.services_up = False
        self.green: list[str] = []     # spec files that pass, repo-relative
        self.filed: dict[str, int] = {}   # scenario -> issue number

    def spec_rel(self, sid: str) -> str:
        return f"tests/{self.suite}/{sid.lower()}.spec.ts"

    def state(self, sid: str, state: str, round_: int | None = None, **extra) -> None:
        self.run.emit("pkg", pkg=sid, state=state, round=round_, **extra)

    def usage(self, sid: str, agent: str, model: str | None, res: agents.Result) -> None:
        self.run.emit("usage", pkg=sid, agent=agent, model=model, **res.usage.as_dict())

    # ---- services and browser ---------------------------------------------------------------------------------
    def ensure_services(self, tag: str = "up") -> agents.Result | None:
        """Start the QA services with the code of this tree. qa.restart (down, then up) wins over qa.up, so a
        service left running from older code never answers the specs."""
        command = self.cfg.get("qa.restart") or self.cfg.get("qa.up")
        if self.services_up or not command:
            return None
        d = self.run.pkg_dir("services")
        res = agents.shell(self.cfg, self.run, None, "services", command, d / f"{tag}.log", env=self.env)
        self.services_up = res.ok
        return res

    def playwright(self, sid: str, tag: str) -> tuple[bool, str, list[Path]]:
        d = self.run.pkg_dir(sid)
        if self.cfg.get("qa.reset"):
            res = agents.shell(self.cfg, self.run, sid, "playwright", self.cfg.get("qa.reset"), d / f"reset-{tag}.log",
                               env=self.env)
            if not res.ok:
                return False, "qa reset failed:\n" + res.text, []
        results = self.qa_dir / self.cfg.get("qa.results_dir", "test-results")
        shutil.rmtree(results, ignore_errors=True)
        command = self.cfg.get("qa.run", "cd qa && npx playwright test {spec} --reporter=line").format(
            spec=self.spec_rel(sid), spec_path=f"{self.qa_dir.name}/{self.spec_rel(sid)}")
        res = agents.shell(self.cfg, self.run, sid, "playwright", command, d / f"playwright-{tag}.log", env=self.env,
                           timeout=float(self.cfg.get("qa.timeout_seconds", 900)))
        kept: list[Path] = []
        if results.is_dir():
            dest = d / f"results-{tag}"
            for path in results.rglob("*"):
                if path.is_file() and path.suffix in (".md", ".png", ".zip", ".txt"):
                    target = dest / path.relative_to(results)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    kept.append(target)
        return res.ok, res.text, kept

    # ---- one scenario --------------------------------------------------------------------------------------------
    def scenario(self, sid: str) -> str:
        """done | app_bug | env | failed."""
        d = self.run.pkg_dir(sid)
        values = dict(scenario=sid, suite=self.suite_rel, spec=f"{self.qa_dir.name}/{self.spec_rel(sid)}")
        prompt = render("qa_write", **values)
        for round_ in range(self.max_rounds + 1):
            self.state(sid, "codex", round_)
            res = agents.codex(self.cfg, self.run, sid, "codex", prompt, d / f"codex-{round_}")
            self.usage(sid, "codex", self.cfg.get("models.codex"), res)
            if not res.ok:
                self.state(sid, "failed", round_, message=f"codex exit {res.rc}")
                return "failed"
            allowed = self.cfg.get("qa.codex_may_change", r"^qa/")
            outside = [p for p in gitops.changed(self.cfg.root) if not re.search(allowed, p)]
            spec_file = self.qa_dir / self.spec_rel(sid)
            if outside or not spec_file.is_file():
                findings = "\n".join(
                    [f"{i}. {p} - changed outside qa/ - revert it; QA changes only the spec and qa/ helpers"
                     for i, p in enumerate(outside, 1)]
                    + ([] if spec_file.is_file() else [f"{len(outside) + 1}. {values['spec']} - missing - write it"]))
                self.run.emit("findings", pkg=sid, round=round_, text=findings)
                prompt = render("qa_fix", findings=findings, **values)
                continue
            up = self.ensure_services()
            if up is not None and not up.ok:
                self.state(sid, "failed", round_, message="qa services did not start:\n" + up.text[-1500:])
                return "env"
            self.state(sid, "playwright", round_)
            ok, output, artifacts = self.playwright(sid, str(round_))
            self.run.emit("result", pkg=sid, step="playwright", round=round_, ok=ok,
                          summary=(output.splitlines() or [""])[-1][:200])
            verdict_path = d / f"verdict-{round_}.md"
            verdict_path.unlink(missing_ok=True)
            (d / f"playwright-{round_}.tail.txt").write_text(output, encoding="utf-8")
            if ok:
                self.state(sid, "review", round_)
                res = agents.claude(self.cfg, self.run, sid, "review",
                                    render("qa_review", verdict=str(verdict_path), **values), self.model,
                                    d / f"review-{round_}.log")
                self.usage(sid, "claude", self.model, res)
                verdict = verdict_path.read_text(encoding="utf-8") if verdict_path.is_file() else ""
                if verdict.startswith("VERDICT: PASS"):
                    return self.passed(sid, round_)
                findings = "\n".join(line for line in verdict.splitlines() if not line.startswith("VERDICT")) \
                    or "1. The review wrote no verdict; re-check the spec against the scenario."
            else:
                self.state(sid, "triage", round_)
                context = "\n".join(str(p) for p in artifacts if p.name == "error-context.md" or p.suffix == ".png")
                issue_file = d / f"issue-{round_}.md"
                res = agents.claude(self.cfg, self.run, sid, "triage",
                                    render("triage", verdict=str(verdict_path),
                                           output=str(d / f"playwright-{round_}.tail.txt"), artifacts=context or "none",
                                           issue_file=str(issue_file), plan=self.plan or "-", part=self.part or "-",
                                           commit=gitops.git(self.cfg.root, "rev-parse", "--short", "HEAD"),
                                           seed=(self.env or {}).get("QA_SEED", "shop"), **values),
                                    self.model, d / f"triage-{round_}.log")
                self.usage(sid, "claude", self.model, res)
                verdict = verdict_path.read_text(encoding="utf-8") if verdict_path.is_file() else ""
                first = verdict.splitlines()[0].strip() if verdict.strip() else ""
                self.run.emit("result", pkg=sid, step="triage", round=round_, ok=False, summary=first or "no verdict")
                tests = [line for line in verdict.splitlines() if line.lstrip().startswith("[TEST]")]
                apps = [line for line in verdict.splitlines() if line.lstrip().startswith("[APP]")]
                envs = [line for line in verdict.splitlines() if line.lstrip().startswith("[ENV]")]
                if envs:
                    self.state(sid, "failed", round_, message="QA stack problem: " + envs[0][:300])
                    return "env"
                if apps and not tests:
                    self.file_issue(sid, apps[0], issue_file)
                    self.state(sid, "app_bug", round_, message=apps[0][:200])
                    return "app_bug"
                findings = "\n".join(tests) or "1. Triage wrote no verdict; read the Playwright output, fix the spec."
            (d / f"findings-{round_}.md").write_text(findings, encoding="utf-8")
            self.run.emit("findings", pkg=sid, round=round_, text=findings[:4000])
            if round_ >= self.max_rounds:
                self.state(sid, "failed", round_, message=f"spec still wrong after {self.max_rounds} rounds")
                return "failed"
            prompt = render("qa_fix", findings=findings, **values)
        return "failed"

    def passed(self, sid: str, round_: int) -> str:
        spec = f"{self.qa_dir.name}/{self.spec_rel(sid)}"
        self.green.append(spec)
        if not self.commit_specs:
            self.state(sid, "done", round_, message="spec passes")
            return "done"
        sha = gitops.commit_all(self.cfg.root, f"qa: scenario {sid} of {self.suite}")
        name = gitops.branch(self.cfg.root)
        if self.cfg.get("git.push", True):
            gitops.push(self.cfg.root, name)
        self.state(sid, "done", round_, commit=sha, branch=name)
        return "done"

    def file_issue(self, sid: str, finding: str, issue_file: Path) -> None:
        """An [APP] failure becomes an issue labelled qa (once per open scenario issue)."""
        title = f"QA {self.suite} {sid}: {finding.split(' - ')[-1].strip()[:120]}"
        body = issue_file.read_text(encoding="utf-8") if issue_file.is_file() else f"### Actual\n{finding}\n"
        cli = forge.cli(self.cfg)
        try:
            prefix = f"QA {self.suite} {sid}:"
            same = [i for i in cli.issues(label="qa", state="open") if i.title.startswith(prefix)]
            if same:
                cli.comment(same[0].number, f"Still failing at `{gitops.git(self.cfg.root, 'rev-parse', '--short', 'HEAD')}`"
                                            f":\n{finding}\n\n<!-- devchain:qa-again -->")
                self.filed[sid] = same[0].number
                return
            labels = ["qa", *([f"plan:{self.plan}"] if self.plan else [])]
            self.filed[sid] = cli.create(title, body, labels)
        except forge.ForgeError as exc:
            self.run.emit("note", pkg=sid, text=f"could not file the QA issue: {exc}")

    # ---- whole run -------------------------------------------------------------------------------------------------
    def run_all(self) -> tuple[str, str]:
        if not self.scenarios:
            return "failed", f"no scenarios (headings '## S1 ...') in {self.suite_rel}"
        if self.commit_specs:
            if gitops.branch(self.cfg.root) == self.cfg.get("git.base", "main"):
                return "failed", "refusing to run on the base branch; check out the plan branch"
            if not gitops.is_clean(self.cfg.root):
                return "failed", "working tree is not clean"
        for sid in self.scenarios:
            self.run.emit("pkg", pkg=sid, state="waiting")
        results = {}
        for sid in self.scenarios:
            results[sid] = self.scenario(sid)
            if results[sid] == "env":
                return "failed", f"{sid}: the QA stack is wrong, not the app (triage: {self.run.pkg_dir(sid)})"
        bugs = {sid: self.filed.get(sid) for sid, r in results.items() if r == "app_bug"}
        failed = [sid for sid, r in results.items() if r == "failed"]
        if bugs:
            return "app_bug", "app bugs filed: " + ", ".join(f"{s} #{n}" if n else s for s, n in bugs.items())
        if failed:
            return "failed", f"specs still wrong: {', '.join(failed)}"
        return "done", "all scenarios pass"
