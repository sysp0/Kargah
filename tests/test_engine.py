import json

from engine_fixtures import EXPORT, MULTIPLY_CODE, MULTIPLY_TEST, git, make_world, multiply_feature, says, writes

from kargah.ports.harness import HarnessResult

PASS = "VERDICT: PASS\nSHOULD: add a docstring"
MUST_FIX = "VERDICT: MUST_FIX\nMUST-FIX: multiply ignores floats in the docs"


def labels(world, n=1):
    return set(world.tracker.get_ticket(n).labels)


def start(world, body="add multiply(a, b)"):
    n = world.tracker.open_ticket("add multiply", body, ("ready",))
    return n


def test_happy_path_ends_in_needs_human_with_proof_and_log(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    start(w)
    assert w.engine.tick() == "needs-human"
    assert labels(w) == {"needs-human"}
    assert w.host.ready == ["kargah/1"]
    history = w.remote_log("kargah/1")
    assert "Kargah-State: complete" in history and "Kargah-Issue: #1" in history
    [line] = w.log()
    record = json.loads(line)
    assert record["outcome"] == "needs-human" and record["reviews"] == 1 and record["ticket"] == 1


def test_tests_that_pass_without_the_change_are_not_accepted(tmp_path):
    lazy = writes({"tests/test_lazy.py": "def test_x():\n    assert 1 == 1\n"})
    w = make_world(tmp_path, [lazy] * 6, [])        # 3 tries by Codex, then 3 by Claude (the one escalation)
    start(w)
    assert w.engine.tick() == "blocked"
    assert "blocked" in labels(w)
    assert "do not guard it" in w.builder.calls[1].prompt


def test_must_fix_goes_to_rework_then_passes(tmp_path):
    fixed = writes({"src/calc/ops.py": MULTIPLY_CODE + "\n# floats ok\n"})
    w = make_world(tmp_path, [multiply_feature(), fixed], [says(MUST_FIX), says(PASS)])
    start(w)
    assert w.engine.tick() == "needs-human"
    assert "multiply ignores floats" in w.builder.calls[1].prompt
    assert len(w.reviewer.calls) == 2


def test_rework_is_capped_then_blocked(tmp_path):
    edit = lambda i: writes({"src/calc/ops.py": MULTIPLY_CODE + f"\n# {i}\n"})  # noqa: E731
    w = make_world(tmp_path, [multiply_feature(), *[edit(i) for i in range(1, 5)]], [says(MUST_FIX)] * 5)   # 3 reworks + 1 Claude
    start(w)
    assert w.engine.tick() == "blocked"


def test_a_question_waits_for_the_owner_and_resumes_on_the_answer(tmp_path):
    w = make_world(tmp_path, [says("QUESTION: ints or floats?"), multiply_feature()], [says(PASS)])
    n = start(w)
    assert w.engine.tick() == "question" and labels(w) == {"needs-info"}
    assert w.engine.tick() == "idle"            # nobody answered: the bot never answers itself
    w.tracker.human_says(n, "floats please")
    assert w.engine.tick() == "needs-human"
    assert "floats please" in w.builder.calls[1].prompt


def test_usage_limit_saves_a_draft_commit_and_resumes_after_the_reset(tmp_path):
    from datetime import timedelta
    clock_holder = {}

    def limited(request):
        (request.cwd / "tests").mkdir(exist_ok=True)
        (request.cwd / "tests/test_multiply.py").write_text(MULTIPLY_TEST)
        return HarnessResult(ok=False, limited=True, resets_at=clock_holder["w"].clock.now + timedelta(hours=1))

    w = make_world(tmp_path, [limited, multiply_feature()], [says(PASS)])
    clock_holder["w"] = w
    start(w)
    assert w.engine.tick() == "limit"
    assert "Kargah-State: incomplete" in w.remote_log("kargah/1")
    assert w.engine.tick() == "idle"            # still before the reset time
    w.clock.advance(hours=2)
    assert w.engine.tick() == "needs-human"


def test_limit_without_a_time_blocks_instead_of_guessing(tmp_path):
    w = make_world(tmp_path, [lambda r: HarnessResult(ok=False, limited=True)], [])
    start(w)
    assert w.engine.tick() == "limit-unknown" and "blocked" in labels(w)


def test_reviewer_limit_never_skips_the_review(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [lambda r: HarnessResult(ok=False, limited=True,
                                                                           resets_at=None)])
    start(w)
    assert w.engine.tick() == "limit-unknown"
    assert w.host.ready == []


def test_interrupt_label_stops_the_run_and_waits_for_the_owner(tmp_path):
    holder = {}

    def interrupting(request):
        holder["w"].tracker.add_label(1, "interrupt")
        return multiply_feature()(request)

    w = make_world(tmp_path, [interrupting, multiply_feature()], [says(PASS)])
    holder["w"] = w
    n = start(w)
    assert w.engine.tick() == "interrupted"
    assert labels(w) == {"needs-info"}
    w.tracker.human_says(n, "use the existing helper instead")
    assert w.engine.tick() == "needs-human"


def test_decision_comments_become_files_in_the_branch(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    n = start(w)
    w.tracker.human_says(n, "/decision never use floats in money code")
    assert w.engine.tick() == "needs-human"
    files = git(w.remote, "ls-tree", "-r", "--name-only", "kargah/1")
    assert "docs/decisions/1-" in files


def test_a_busy_lock_means_no_second_run(tmp_path):
    from kargah.orchestrator.lock import RunLock
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    start(w)
    with RunLock(tmp_path / "work" / "state" / "run.lock") as held:
        assert held.acquired and w.engine.tick() == "busy"
    assert w.engine.tick() == "needs-human"


def test_nothing_ready_is_idle(tmp_path):
    w = make_world(tmp_path, [], [])
    w.tracker.open_ticket("not ready")
    assert w.engine.tick() == "idle"


def test_rework_that_changes_nothing_blocks_instead_of_looping(tmp_path):
    w = make_world(tmp_path, [multiply_feature(), says("nothing to change")], [says(MUST_FIX)])
    start(w)
    assert w.engine.tick() == "blocked"
    assert len(w.builder.calls) == 2


def test_resume_after_a_question_with_no_new_change_completes_the_wip_commit(tmp_path):
    ask = writes({"tests/test_multiply.py": MULTIPLY_TEST, "src/calc/ops.py": MULTIPLY_CODE,
                  "src/calc/__init__.py": EXPORT}, text="QUESTION: ints or floats?")
    w = make_world(tmp_path, [ask, says("nothing to change, go on as is")], [says(PASS)])
    n = start(w)
    assert w.engine.tick() == "question"
    w.tracker.human_says(n, "go on as is")
    assert w.engine.tick() == "needs-human"
    state = git(w.remote, "log", "-1", "--format=%(trailers:key=Kargah-State,valueonly)", "kargah/1")
    assert state == "complete"


def test_interrupt_label_set_while_the_agent_runs_stops_it_and_saves_a_wip_commit(tmp_path):
    holder = {}

    def long_running(request):
        multiply_feature()(request)
        holder["w"].tracker.add_label(1, "interrupt")      # the owner reacts while the agent works
        assert request.should_stop()
        return HarnessResult(ok=False, stopped=True)

    w = make_world(tmp_path, [long_running], [])
    holder["w"] = w
    start(w)
    assert w.engine.tick() == "interrupted"
    assert labels(w) == {"needs-info"}
    assert "Kargah-State: incomplete" in w.remote_log("kargah/1")
    assert w.reviewer.calls == []


def test_interrupt_label_set_while_the_reviewer_runs_ends_the_run(tmp_path):
    holder = {}

    def reviewing(request):
        holder["w"].tracker.add_label(1, "interrupt")
        assert request.should_stop()
        return HarnessResult(ok=False, stopped=True)

    w = make_world(tmp_path, [multiply_feature()], [reviewing])
    holder["w"] = w
    start(w)
    assert w.engine.tick() == "interrupted"
    assert labels(w) == {"needs-info"} and w.host.ready == []


def test_a_run_records_one_step_per_agent_call_and_a_run_record_with_costs(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    start(w)
    assert w.engine.tick() == "needs-human"
    steps = [json.loads(line) for line in (tmp_path / "work" / "steps.jsonl").read_text().splitlines()]
    assert [(s["step_id"], s["role"], s["status"]) for s in steps] == [("r1-01", "implement", "ok"),
                                                                       ("r1-02", "review", "ok")]
    folder = tmp_path / "work" / "runs" / "r1"
    assert "multiply" in (folder / "r1-01" / "diff.patch").read_text()
    assert "add multiply" in (folder / "r1-01" / "prompt.md").read_text()
    assert (folder / "r1-02" / "reply.md").read_text() == PASS and not (folder / "r1-02" / "diff.patch").exists()
    record = json.loads(w.log()[0])
    assert (record["kind"], record["steps"], record["cost_unknown_steps"], record["cost_usd"]) == ("run", 2, 2, 0.0)
    assert steps[0]["base_sha"] and steps[0]["head_sha"] and steps[0]["harness"] == "scripted"


def test_old_step_folders_are_pruned_at_the_start_of_a_tick(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    start(w)
    w.engine.tick()
    w.clock.advance(days=31)
    assert w.engine.tick() == "idle"
    assert not (tmp_path / "work" / "runs" / "r1").exists()
    assert len((tmp_path / "work" / "steps.jsonl").read_text().splitlines()) == 2
