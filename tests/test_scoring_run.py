import json

from engine_fixtures import SEED, make_world, multiply_feature, says
from test_scorers import GOOD

from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DefaultBranchSource
from kargah.orchestrator.scoring import Scoring
from kargah.ports.harness import HarnessResult

PASS = "VERDICT: PASS"
ALWAYS = GOOD.replace("sampling_rate = 10", "sampling_rate = 100")
FILES = {".kargah/scorers/mine/scorer.md": ALWAYS}
JUDGE_OK = "LABEL: yes\nREASON: it does what the ticket says"


def world(tmp_path, judge_steps, files=FILES, builder=None):
    w = make_world(tmp_path, builder if builder is not None else [multiply_feature()], [says(PASS)], files, judge_steps)
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "needs-human"
    return w


def scores(tmp_path):
    path = tmp_path / "work" / "scores.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def steps(tmp_path):
    return [json.loads(line) for line in (tmp_path / "work" / "steps.jsonl").read_text().splitlines()]


def test_a_finished_step_is_graded_after_the_main_work_with_a_prompt_from_the_records(tmp_path):
    w = world(tmp_path, [says(JUDGE_OK)])             # the tick that ran the ticket graded its finished step
    assert w.engine.tick() == "idle"
    [record] = scores(tmp_path)
    assert (record["scorer"], record["step_id"], record["label"], record["score"], record["passed"]) == \
        ("mine", "r1-01", "yes", 1.0, True)
    assert record["role"] == "implement" and record["manual"] is False and record["reason"].startswith("it does")
    [call] = w.planner.calls
    assert call.role == "judge" and call.cwd != w.builder.calls[0].cwd and not (call.cwd / "src").exists()
    for needle in ("Judge it.", "- `yes`: d", "add multiply(a, b)", "+def multiply", "LABEL: <value>"):
        assert needle in call.prompt
    judge = [s for s in steps(tmp_path) if s["role"] == "judge"]
    assert len(judge) == 1 and record["judge_step"] == judge[0]["step_id"]


def test_a_step_is_graded_once_and_judge_steps_are_never_graded(tmp_path):
    both = {".kargah/scorers/mine/scorer.md": ALWAYS.replace('agents = ["implement"]', 'agents = ["implement", "judge"]')}
    w = world(tmp_path, [says(JUDGE_OK)], both)
    w.engine.tick()
    w.engine.tick()
    w.engine.tick()
    assert len(scores(tmp_path)) == 1 and len(w.planner.calls) == 1


def test_builtin_scorers_are_off_and_nothing_is_graded_by_default(tmp_path):
    w = world(tmp_path, [], files={})
    assert w.engine.tick() == "idle" and w.planner.calls == [] and scores(tmp_path) == []


def test_an_invalid_judge_answer_is_asked_again_then_recorded_as_invalid(tmp_path):
    w = world(tmp_path, [says("hmm"), says("LABEL: ??")])
    [record] = scores(tmp_path)
    assert record["label"] is None and record["passed"] is False and record["reason"] == "invalid judge output"
    assert "did not follow the format" in w.planner.calls[1].prompt


def test_a_usage_limit_writes_nothing_and_the_next_tick_tries_again(tmp_path):
    w = world(tmp_path, [lambda r: HarnessResult(ok=False, limited=True), says(JUDGE_OK)])
    assert scores(tmp_path) == []
    w.engine.tick()
    assert len(scores(tmp_path)) == 1


def test_manual_scoring_ignores_the_sampling_rate_and_a_rescore_replaces_the_old_record(tmp_path):
    never = {".kargah/scorers/mine/scorer.md": ALWAYS.replace("sampling_rate = 100", "sampling_rate = 0")}
    w = world(tmp_path, [says("LABEL: no\nREASON: bad"), says(JUDGE_OK)], never)
    assert scores(tmp_path) == []
    definition = load_definition(DefaultBranchSource(w.engine._s.workspace))
    step = w.engine._s.runs.steps()[0]
    scoring = Scoring(w.engine._s)
    assert scoring.score_step(definition, definition.scorers["mine"], step, manual=True)
    assert scoring.score_step(definition, definition.scorers["mine"], step, manual=True)
    first, second = scores(tmp_path)
    assert (first["label"], first["manual"], second["label"]) == ("no", True, "yes")
    from kargah.domain.metrics import compute
    from datetime import UTC, datetime
    report = compute([], [], [], scores(tmp_path), None, datetime.now(UTC))
    assert report["scorers"]["mine"] == {"count": 1, "pass_rate": 1.0, "labels": {"yes": 1}}


def test_at_most_three_steps_are_graded_per_tick(tmp_path):
    w = world(tmp_path, [says(JUDGE_OK)] * 5)
    store = w.engine._s.runs
    base = store.steps()[0]
    from dataclasses import replace
    for i in range(2, 6):                                         # four more finished implement steps
        store.save_step(replace(base, step_id=f"r1-0{i + 1}"), {"ticket.md": "t"})
    w.engine.tick()
    assert len(scores(tmp_path)) == 4                              # one from the first tick, three from this one
    w.engine.tick()
    assert len(scores(tmp_path)) == 5


def test_steps_of_a_run_that_has_not_finished_are_not_graded(tmp_path):
    w = world(tmp_path, [says(JUDGE_OK)] * 2)
    from dataclasses import replace
    w.engine._s.runs.save_step(replace(w.engine._s.runs.steps()[0], run="unfinished", step_id="unfinished-01"), {})
    w.engine.tick()
    assert {s["run"] for s in scores(tmp_path)} == {"r1"}


def test_the_score_command_grades_one_step_by_hand(tmp_path, monkeypatch, capsys):
    from kargah.orchestrator import cli
    w = world(tmp_path, [says(JUDGE_OK)], {".kargah/scorers/mine/scorer.md": ALWAYS.replace("sampling_rate = 100", "sampling_rate = 0")})
    monkeypatch.setattr(cli, "build_services", lambda *a, **k: w.engine._s)
    assert cli.main(["score", "--workdir", str(tmp_path / "work"), "--step", "r1-01", "--scorer", "mine"]) == 0
    assert capsys.readouterr().out.strip() == "mine: scored" and scores(tmp_path)[0]["manual"] is True
    assert cli.main(["score", "--workdir", str(tmp_path / "work"), "--step", "r1-02", "--scorer", "mine"]) == 2     # mine grades implement only
    assert cli.main(["score", "--workdir", str(tmp_path / "work"), "--step", "nope"]) == 2
