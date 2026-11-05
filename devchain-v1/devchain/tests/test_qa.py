import json
import subprocess

from devchain import cli
from devchain import events as ev
from devchain.config import load
from devchain.qa import QA

SPEC = "qa/tests/suite/s1.spec.ts"
SPEC2 = "qa/tests/suite/s2.spec.ts"
REVIEW_PASS = {"verdict": "VERDICT: PASS"}


def test_configured_qa_port_reaches_stack_reset_and_browser(repo):
    cfg = load(repo.root)
    cfg.data["qa"]["env"] = {"QA_UI_PORT": "5203"}
    cfg.data["qa"]["restart"] = 'test "$QA_UI_PORT" = 5203'
    cfg.data["qa"]["reset"] = 'test "$QA_UI_PORT" = 5203'
    cfg.data["qa"]["run"] = 'test "$QA_UI_URL" = http://localhost:5203'
    qa = QA(cfg, ev.create(cfg.runs_dir, "qa"), "suite", [])
    assert qa.ensure_services().ok
    assert qa.playwright("S1", "port")[0]


def test_worktree_port_and_explicit_browser_url_override_defaults(repo):
    cfg = load(repo.root)
    cfg.data["qa"]["env"] = {"QA_UI_PORT": "5203"}
    run = ev.create(cfg.runs_dir, "qa")
    qa = QA(cfg, run, "suite", [], env={"QA_UI_PORT": "5193"})
    assert qa.env["QA_UI_URL"] == "http://localhost:5193"
    qa = QA(cfg, run, "suite", [], env={"QA_UI_PORT": "5193", "QA_UI_URL": "http://example.test"})
    assert qa.env["QA_UI_URL"] == "http://example.test"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout.strip()


def states(events, pkg):
    return [e["state"] for e in events if e["type"] == "pkg" and e.get("pkg") == pkg]


def on_branch(repo):
    git(repo.root, "checkout", "-q", "-b", "plan/x")


def issues(repo):
    path = repo.fake / "gh.json"
    return json.loads(path.read_text()) if path.exists() else []


def test_test_bug_goes_back_to_codex_then_passes(repo):
    on_branch(repo)
    repo.codex({"write": {SPEC: "BAD"}}, {"write": {SPEC: "OK"}})
    repo.claude({"verdict": "VERDICT: TEST\n[TEST] qa/tests/suite/s1.spec.ts:3 - wrong label - use the Persian label"},
                REVIEW_PASS)
    assert cli.main(["qa", "suite", "S1"]) == 0
    assert "wrong label" in repo.prompt("codex", 1)
    assert "error-context.md" in repo.prompt("claude", 0)
    assert states(repo.events(), "S1")[-1] == "done"
    assert git(repo.root, "log", "-1", "--format=%s") == "qa: scenario S1 of suite"


def test_app_bug_files_a_qa_issue_and_changes_no_app_code(repo):
    on_branch(repo)
    repo.codex({"write": {SPEC: "OK NEEDS_APP"}})
    repo.claude({"verdict": "VERDICT: APP\n[APP] qa/tests/suite/s1.spec.ts:3 - label - missing in the app"})
    assert cli.main(["qa", "suite", "S1"]) == 3
    assert "app_bug" in states(repo.events(), "S1")
    found = issues(repo)
    assert len(found) == 1 and found[0]["title"].startswith("QA suite S1:")
    assert "qa" in [lab["name"] if isinstance(lab, dict) else lab for lab in found[0]["labels"]]
    assert repo.calls("codex") == 1


def test_a_failing_app_again_comments_on_the_open_issue(repo):
    on_branch(repo)
    for _ in range(2):
        for name in ("codex.count", "claude.count"):
            (repo.fake / name).unlink(missing_ok=True)
        repo.codex({"write": {SPEC: "OK NEEDS_APP"}})
        repo.claude({"verdict": "VERDICT: APP\n[APP] s1 - label - missing"})
        cli.main(["qa", "suite", "S1"])
        git(repo.root, "checkout", "-q", "--", ".")
        git(repo.root, "clean", "-fdq", "qa")
    found = issues(repo)
    assert len(found) == 1 and "qa-again" in json.dumps(found[0])


def test_env_verdict_stops_the_run(repo):
    on_branch(repo)
    repo.codex({"write": {SPEC: "OK NEEDS_APP"}})
    repo.claude({"verdict": "VERDICT: ENV\n[ENV] a foreign server holds :5173"})
    assert cli.main(["qa", "suite"]) == 3
    events = repo.events()
    assert states(events, "S1")[-1] == "failed" and states(events, "S2") == ["waiting"]
    assert not issues(repo)


def test_codex_may_not_touch_app_code_in_qa(repo):
    on_branch(repo)
    repo.codex({"write": {SPEC: "OK", "app/x.py": "bad"}}, {"write": {SPEC: "OK", "app/x.py": ""}})
    repo.claude(REVIEW_PASS)
    cli.main(["qa", "suite", "S1"])
    assert "app/x.py - changed outside qa/" in repo.prompt("codex", 1)


def test_all_scenarios_by_default(repo):
    on_branch(repo)
    repo.codex({"write": {SPEC: "OK"}}, {"write": {SPEC2: "OK"}})
    repo.claude(REVIEW_PASS)
    assert cli.main(["qa", "suite"]) == 0
    events = repo.events()
    assert states(events, "S1")[-1] == "done" and states(events, "S2")[-1] == "done"


def test_the_base_branch_is_refused(repo):
    assert cli.main(["qa", "suite", "S1"]) == 3
    run = ev.open_run(repo.root / ".devchain/runs", None)
    finished = [e for e in ev.read(run.events_path)[0] if e["type"] == "run_finished"][-1]
    assert "base branch" in finished["message"]


def test_a_run_started_by_an_agent_is_refused(repo, monkeypatch):
    monkeypatch.setenv("DEVCHAIN_NESTED", "1")
    assert cli.main(["qa", "suite", "S1"]) == 2
    assert repo.calls("codex") == 0


def test_qaloop_tests_a_finished_part_once_and_commits_green_specs(repo):
    from devchain import config, plan as plan_mod
    from devchain.journal import Journal
    from devchain.qaloop import QaLoop

    folder = repo.root / "docs/devchain-plan/x"
    folder.mkdir(parents=True)
    (folder / "01-a.md").write_text("QA: suite S1\n\n| Pn | Title | files | acceptance |\n|---|---|---|---|\n"
                                    "| P1 | One | `src/a.py` | t |\n")
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "plan")
    cfg = config.load(repo.root)
    loop = QaLoop(cfg, "x", Journal(ev.create(cfg.runs_dir, "loop"), repo.root / ".devchain/logs/x.log"))
    plan = plan_mod.read(cfg, "x")
    assert loop.due(plan, set()) is None
    assert loop.due(plan, {"P1"}) == ("01-a.md", "suite", ["S1"])
    loop.remember("01-a.md", "abc")
    assert loop.due(plan, {"P1"}) is None
    loop.where = repo.root.parent / "qa-tree"
    (loop.where / SPEC).parent.mkdir(parents=True)
    (loop.where / SPEC).write_text("OK")
    loop.ready.append(("01-a.md", [SPEC]))
    loop.collect()
    assert git(repo.root, "log", "-1", "--format=%s") == "qa: specs of 01-a.md pass"
