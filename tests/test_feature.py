"""Feature.package: one task built by Codex, checked outside the sandbox, reviewed by Claude, committed."""
from conftest import git
from helpers import FIX, FOLDER, NOTE, PART, PASS, feature, setup, states, work

from kargah import agents, events, gitops

WAIT = {"write": {NOTE: "1) row P1 unclear\n"}, "blocked": f"plan problem, see {NOTE}"}


def test_pass_commits_with_trailers_and_pushes(repo):
    setup(repo)
    repo.codex(work("a"))
    repo.claude(PASS)
    f = feature(repo)
    assert f.package("P1") == "done"
    assert git(repo.root, "log", "-1", "--format=%s") == "feat: done"
    body = git(repo.root, "log", "-1", "--format=%b")
    assert "Package: P1\nPart: 01-demo.md\nTouches: api:a" in body
    assert git(repo.root, "ls-remote", "--heads", "origin", "plan/x")
    assert states(f) == ["codex", "accept", "tests", "review", "commit", "done"]
    assert f.info["sha"] and f.info["session"] == "t"
    usage = [e for e in events.read(f.run.events_path)[0] if e["type"] == "usage"]
    assert {u["agent"] for u in usage} == {"codex", "claude"} and all("log" in u and "rc" in u for u in usage)
    assert "package P1 of docs/devchain-plan/x/01-demo.md" in repo.prompt("codex", 0)


def test_findings_go_back_to_the_same_codex_session(repo):
    setup(repo)
    repo.codex(work("a"), {"write": {"src/a.py": "x = 2\n"}})
    repo.claude(FIX, PASS)
    f = feature(repo)
    assert f.package("P1") == "done"
    assert "exec resume" in repo.argv("codex", 1) and " t -" in repo.argv("codex", 1)
    assert "exec resume" not in repo.argv("codex", 0)
    assert "src/a.py:1 - missing guard" in repo.prompt("codex", 1)


def test_the_next_review_reads_the_last_findings_and_codexs_answer(repo):
    setup(repo)
    repo.codex(work("a"), {"write": {"src/a.py": "x = 2\n"}, "reply": "kept the guard: tests/test_a.py:2 needs it"})
    repo.claude(FIX, PASS)
    assert feature(repo).package("P1") == "done"
    assert "This is the first review of this package." in repo.prompt("claude", 0)
    assert "kept the guard: tests/test_a.py:2 needs it" in repo.prompt("claude", 1)


def test_still_failing_after_the_rounds_is_stuck_with_the_last_findings(repo):
    setup(repo)
    repo.codex(work("a"), {"write": {"src/a.py": "x = 3\n"}})
    repo.claude(FIX)
    f = feature(repo)
    assert f.package("P1") == "stuck"
    assert repo.calls("codex") == 3           # first round + 2 fix rounds
    assert "missing guard" in f.info["question"] and "still failing after 2 fix rounds" in f.info["message"]
    assert states(f)[-1] == "blocked"


def test_a_stuck_task_gets_one_plan_check_then_fresh_rounds(repo):
    setup(repo)
    repo.codex(work("a"), {"write": {"src/a.py": "x = 3\n"}}, {"write": {"src/a.py": "x = 4\n"}})
    repo.claude(FIX, FIX, FIX, {"verdict": "PLANFIX: ANSWER\nthe guard is src/a.py:1 (spec/decisions.md:95)"}, PASS)
    f = feature(repo, planfix=True)
    assert f.package("P1") == "done"
    assert "the guard is src/a.py:1" in repo.prompt("codex", 3)
    assert "exec resume" in repo.argv("codex", 3)


def test_the_second_stuck_goes_to_the_owner(repo):
    setup(repo)
    repo.codex(work("a"), {"write": {"src/a.py": "x = 3\n"}})
    repo.claude(FIX, FIX, FIX, {"verdict": "PLANFIX: ANSWER\nlook at src/a.py:1 (spec/decisions.md:95)"}, FIX)
    f = feature(repo, planfix=True)
    assert f.package("P1") == "stuck"
    assert repo.calls("claude") >= 4 and "missing guard" in f.info["question"]


def test_acceptance_failure_skips_the_review(repo):
    setup(repo)
    repo.codex({"write": {"src/a.py": "x = 1\n", "tests/test_a.py": ""}}, work("a"))
    repo.claude(PASS)
    f = feature(repo)
    assert f.package("P1") == "done"
    assert repo.calls("claude") == 1 and repo.calls("codex") == 2


def test_fast_tests_run_before_the_review_so_a_failure_costs_no_review(repo):
    setup(repo, toml="")
    repo.codex(work("a"), {"write": {"tests/ok": "1\n"}})
    repo.claude(PASS)
    f = feature(repo)
    f.cfg.data["loop"]["test_cmd"] = "test -e tests/ok"
    assert f.package("P1") == "done"
    assert repo.calls("claude") == 1 and repo.calls("codex") == 2
    assert "Fast tests failed" in repo.prompt("codex", 1)


def test_qa_start_failure_stops_before_more_specs_tests_or_fix_agents(repo):
    setup(repo)
    repo.codex(work("a"))
    f = feature(repo, planfix=True)
    smoke = repo.root / "qa/tests/smoke/pages.spec.ts"
    smoke.parent.mkdir(parents=True)
    smoke.write_text("OK")
    f.cfg.data["ui"] = {"dir": "src", "build": "true", "smoke": [str(smoke.relative_to(repo.root))] * 2}
    f.cfg.data["qa"]["restart"] = "echo attempt >> .devchain/service-attempts; echo 'port already in use'; exit 1"
    f.cfg.data["loop"]["test_cmd"] = "touch .devchain/tests-ran"
    assert f.package("P1") == "failed"
    assert "QA services did not start" in f.info["message"]
    assert "port already in use" in f.info["message"]
    assert repo.calls("codex") == 1 and repo.calls("claude") == 0
    assert not (repo.root / ".devchain/tests-ran").exists()
    assert (repo.root / ".devchain/service-attempts").read_text().splitlines() == ["attempt"]


def test_waits_for_a_holder_saves_nothing_in_git_and_names_the_target(repo):
    setup(repo)
    repo.codex({"write": {"src/a.py": "x = 1\n"}, "blocked": "WAITS FOR: #60 - needs the answer on totals"})
    f = feature(repo)
    assert f.package("P1") == "waits"
    assert f.info["target"] == "#60" and "needs the answer" in f.info["message"]
    assert repo.calls("claude") == 0
    assert "Open questions and issues of this plan now: none" in repo.prompt("codex", 0)


def test_a_plan_problem_without_a_plan_check_goes_to_the_owner_with_the_questions(repo):
    setup(repo)
    repo.codex({"write": {NOTE: "# P1\n\n## Questions for the owner\n1. A or B?\n"},
                "blocked": f"plan problem, see {NOTE}"})
    f = feature(repo)
    assert f.package("P1") == "question"
    assert f.info["question"] == "1. A or B?"


def test_plan_check_fixes_the_row_traces_it_commits_and_codex_goes_on(repo):
    setup(repo)
    repo.codex(WAIT, work("a"))
    repo.claude({"verdict": "PLANFIX: FIXED\nP1 lists src/c.py (src/c.py:1 imports a)",
                 "replace": {PART: ["| P1 | One |", "| P1 | One, with c |"]}}, PASS)
    f = feature(repo, planfix=True)
    assert f.package("P1") == "done"
    assert "--effort" in repo.argv("claude", 0) and "fake-opus" in repo.argv("claude", 0)
    assert "plan: P1 fixed by the plan check of P1" in git(repo.root, "log", "--format=%s")
    trace = (repo.root / FOLDER / "trace.md").read_text()
    assert "P1: plan check while building P1: P1 lists src/c.py" in trace
    assert not (repo.root / NOTE).exists() and "Blocked: none" in (repo.root / "docs/progress.md").read_text()
    assert "src/c.py:1 imports a" in repo.prompt("codex", 1) and "exec resume" in repo.argv("codex", 1)
    assert f.row("P1").title == "One, with c"


def test_plan_check_answers_without_a_plan_change(repo):
    setup(repo)
    repo.codex(WAIT, work("a"))
    repo.claude({"verdict": "PLANFIX: ANSWER\nKeep inspection.py: N48 keeps it (spec/decisions.md:95)"}, PASS)
    f = feature(repo, planfix=True)
    assert f.package("P1") == "done"
    assert "N48 keeps it" in repo.prompt("codex", 1)


def test_plan_check_ask_goes_to_the_owner_with_the_topics(repo):
    setup(repo)
    repo.codex({"write": {NOTE: "# P1\n\n## Questions for the owner\n1. A or B?\n"},
                "blocked": f"plan problem, see {NOTE}"})
    repo.claude({"verdict": "PLANFIX: ASK\nN48 does not say\nABOUT: api:a, `table:x`"})
    f = feature(repo, planfix=True)
    assert f.package("P1") == "question"
    assert f.info["about"] == ["api:a", "table:x"] and f.info["question"] == "1. A or B?"


def test_plan_check_that_edits_outside_the_plan_folder_is_undone_and_asks(repo):
    setup(repo)
    repo.codex(WAIT)
    repo.claude({"verdict": "PLANFIX: FIXED", "append": {"spec/decisions.md": "N99\n"}})
    f = feature(repo, planfix=True)
    assert f.package("P1") == "question"
    assert "outside docs/devchain-plan/x: spec/decisions.md" in f.info["message"]
    assert not (repo.root / "spec/decisions.md").exists()


def test_a_plan_fix_that_cites_no_line_is_undone(repo):
    setup(repo)
    repo.codex(WAIT)
    repo.claude({"verdict": "PLANFIX: FIXED\nrow fixed", "append": {PART: "<!-- x -->\n"}})
    f = feature(repo, planfix=True)
    assert f.package("P1") == "question"
    assert "<!-- x -->" not in (repo.root / PART).read_text()


def test_one_task_cannot_use_every_plan_check(repo):
    setup(repo)
    repo.codex(WAIT)
    repo.claude({"verdict": "PLANFIX: FIXED\nrow fixed (spec/decisions.md:95)", "append": {PART: "<!-- f -->\n"}})
    f = feature(repo, planfix=True)
    f.planfix_pkg_max = 2
    assert f.package("P1") == "question"
    assert repo.calls("claude") == 2 and "the 2 plan checks of P1 are used" in f.info["message"]


def test_usage_limit_waits_and_resends_in_the_same_session(repo):
    setup(repo)
    repo.codex({"limit": True}, work("a"))
    repo.claude(PASS)
    f = feature(repo)
    assert f.package("P1") == "done"
    assert repo.calls("codex") == 2
    assert [e["type"] for e in events.read(f.run.events_path)[0] if e["type"].startswith("limit")] == \
        ["limit_wait", "limit_done"]


def test_a_codex_that_never_leaves_the_limit_returns_limit(repo):
    setup(repo)
    repo.codex({"limit": True})
    f = feature(repo)
    f.cfg.data["codex"]["max_tries"] = 2
    assert f.package("P1") == "limit" and f.info["message"] == "still at the usage limit"


def test_a_busy_model_waits_and_resends(repo):
    setup(repo)
    repo.codex({"busy": True}, work("a"))
    repo.claude(PASS)
    assert feature(repo).package("P1") == "done"
    assert repo.calls("codex") == 2


def test_claude_session_limit_waits_and_resends(repo):
    setup(repo)
    repo.codex(work("a"))
    repo.claude({"limit": "You've hit your session limit · resets 4am (Europe/Berlin)"}, PASS)
    f = feature(repo)
    f.cfg.data["codex"]["limit_wait_seconds"] = 0
    assert f.package("P1") == "done"
    assert repo.calls("claude") == 2


def test_a_failing_review_agent_stops_the_task_without_fix_rounds(repo):
    setup(repo)
    repo.codex(work("a"))
    repo.claude({"exit": 1, "say": "Invalid API key"})
    f = feature(repo)
    assert f.package("P1") == "failed"
    assert repo.calls("codex") == 1 and "Invalid API key" in f.info["message"]


def test_codex_that_changes_nothing_fails(repo):
    setup(repo)
    repo.codex({})
    assert feature(repo).package("P1") == "failed"


def test_reset_time_of_a_claude_limit_is_the_next_one_in_its_zone():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 10, 21, 3, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert agents._reset_seconds("limit · resets 4am (Europe/Berlin)", now) == 3600
    assert agents._reset_seconds("limit · resets 2am (Europe/Berlin)", now) == 23 * 3600


def test_a_push_merges_a_fix_the_thread_pushed_meanwhile(repo, tmp_path):
    setup(repo)
    repo.codex(work("a"))
    repo.claude(PASS)
    f = feature(repo)
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.email", "o@example.test")
    git(other, "config", "user.name", "o")
    git(other, "checkout", "-q", "-b", "plan/x", "origin/main")
    (other / "docs/fix.md").write_text("fix\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "thread fix")
    git(other, "push", "-q", "origin", "plan/x")
    assert f.package("P1") == "done"
    assert (repo.root / "docs/fix.md").is_file() and gitops.packages_on_branch(repo.root) == {"P1"}


def test_the_preflight_checks_the_plan_once(repo):
    setup(repo)
    pre = f"{FOLDER}/preflight.md"
    repo.codex({"write": {pre: "PREFLIGHT: CLEAN\n"}})
    f = feature(repo)
    assert f.preflight() == "done" and repo.calls("claude") == 0
    assert "plan: preflight check of every row" in git(repo.root, "log", "--format=%s")
    assert f.preflight() == "done" and repo.calls("codex") == 1


def test_preflight_problems_go_to_the_plan_check_and_its_fix_is_traced(repo):
    setup(repo)
    pre = f"{FOLDER}/preflight.md"
    repo.codex({"write": {pre: "PREFLIGHT: PROBLEMS\n- P1: misses src/c.py (src/c.py:1)\n"}})
    repo.claude({"verdict": "PLANFIX: FIXED\nP1 lists src/c.py", "replace": {PART: ["| P1 | One |", "| P1 | One+c |"]}})
    f = feature(repo, planfix=True)
    assert f.preflight() == "done"
    assert (repo.root / pre).read_text().startswith("PREFLIGHT: CLEAN\n")
    changed = git(repo.root, "show", "--name-only", "--format=", ":/plan: preflight check").split()
    assert sorted(changed) == sorted([PART, pre, f"{FOLDER}/trace.md"])
    assert "P1: preflight" in (repo.root / FOLDER / "trace.md").read_text()


def test_preflight_questions_come_back_as_blocked_with_the_text(repo):
    setup(repo)
    pre = f"{FOLDER}/preflight.md"
    repo.codex({"write": {pre: "PREFLIGHT: PROBLEMS\n- P1: N48 unclear\n"}})
    repo.claude({"verdict": "PLANFIX: ASK"})
    f = feature(repo, planfix=True)
    assert f.preflight() == "blocked"
    assert "N48 unclear" in f.info["question"] and "questions for the owner" in f.info["message"]
    assert f.preflight() == "blocked"  # committed questions must survive a restart


def ui_plan():
    from helpers import PLAN

    return PLAN.replace("| P1 | One |", "| P1 | UI: One |")


def test_a_ui_row_is_designed_built_from_its_spec_and_reviewed_on_screenshots(repo):
    setup(repo, plan=ui_plan())
    spec = f"{FOLDER}/ui-P1.md"
    shots = "qa/tests/ui/x-p1.spec.ts"
    repo.codex(work("a") | {}, {"write": {"ui/x.js": "1\n"}})
    repo.claude({"verdict": None, "append": {spec: "# UI spec P1\n## Capture\n1. x\n\nUI SPEC: WRITTEN\n"}}, PASS)
    f = feature(repo)
    f.cfg.data["ui"] = {"dir": "ui", "build": "true"}
    # the shots spec is a Playwright spec: the fake QA run is `cd qa && python3 ../check_spec.py {spec}`
    (repo.root / "qa/tests/ui").mkdir(parents=True, exist_ok=True)
    assert f.is_ui("P1")
    assert f.ui_ready("P1") is None
    assert "UI SPEC: WRITTEN" in (repo.root / spec).read_text()
    assert f.ui_values("P1")["shots_spec"] == shots


def test_a_ui_spec_with_open_questions_asks_the_owner_before_codex(repo):
    setup(repo, plan=ui_plan())
    spec = f"{FOLDER}/ui-P1.md"
    repo.claude({"verdict": None, "append": {spec: "# UI spec P1\n## Open questions\n1. Which colour?\n\nUI SPEC: ASK\n"}})
    f = feature(repo)
    assert f.package("P1") == "question"
    assert "Which colour?" in f.info["question"] and repo.calls("codex") == 0


def test_package_test_gate_uses_its_updated_configuration(repo):
    from helpers import PLAN

    setup(repo, plan=PLAN.replace('`src/a.py`, `tests/test_a.py`', '`src/a.py`, `tests/test_a.py`, `devchain.toml`'))
    updated = (repo.root / "devchain.toml").read_text().replace('test_cmd = "true"', 'test_cmd = "touch .devchain/gate-ran"')
    action = work("a")
    action["write"]["devchain.toml"] = updated
    repo.codex(action)
    repo.claude(PASS)
    f = feature(repo)
    assert f.package("P1") == "done"
    assert (repo.root / ".devchain/gate-ran").is_file()
