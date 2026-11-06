import json
from dataclasses import replace

import pytest
from engine_fixtures import SEED, git, make_world, multiply_feature, says, writes
from test_bench_files import SUITE, TASK

from kargah.adapters.factory_files import load_definition
from kargah.adapters.file_sources import DefaultBranchSource, DirSource
from kargah.errors import KargahError
from kargah.orchestrator.bench import BenchRunner, add_task
from kargah.orchestrator.lock import RunLock
from kargah.ports.harness import HarnessResult

PASS_JUDGE = says("LABEL: pass\nREASON: ok")
PARTIAL_JUDGE = says("LABEL: partial\nREASON: half")


def costly(cost):
    def step(request):
        return replace(multiply_feature()(request), cost_usd=cost)
    return step


def bench_world(tmp_path, cheap, pricey, judge_steps, suite=SUITE.replace('scorers = ["task-compliance"]', "scorers = []")):
    w = make_world(tmp_path, [], [], None, judge_steps)
    remote, seed = w.remote, tmp_path / "seed"
    sha = git(remote, "rev-parse", "main")
    for rel, text in {".kargah/benchmarks/small/suite.toml": suite,
                      ".kargah/benchmarks/small/tasks/multiply.toml": TASK.replace("a" * 40, sha)}.items():
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_text(text)
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "suite")
    git(seed, "push", "-q", str(remote), "main")
    by_model = {"": pricey, "claude-sonnet-5-5": cheap}
    s = replace(w.engine._s, harness_for=lambda spec: w.planner if spec.role == "judge" else by_model[spec.model])
    s.workspace.refresh()
    from engine_fixtures import Scripted
    return w, s, sha, Scripted


def runner(w, s, tmp_path):
    return BenchRunner(s, tmp_path / "work", tmp_path / "work" / "state"), load_definition(DefaultBranchSource(s.workspace))


def results(tmp_path):
    return [json.loads(x) for x in (tmp_path / "work" / "bench" / "results.jsonl").read_text().splitlines()]


def scripted(*steps):
    from engine_fixtures import Scripted
    return Scripted(list(steps))


def test_two_configurations_are_compared_and_the_best_is_recommended(tmp_path):
    # the settings: `codex-default` has model "" (pricey); `claude-sonnet` has model claude-sonnet-5-5 (cheap)
    pricey, cheap = scripted(costly(1.0), costly(1.0)), scripted(costly(0.1), costly(0.1))
    w, s, sha, _ = bench_world(tmp_path, cheap, pricey, [PASS_JUDGE, PARTIAL_JUDGE, PASS_JUDGE, PARTIAL_JUDGE])
    refs = git(w.remote, "for-each-ref")
    bench, definition = runner(w, s, tmp_path)
    text = bench.run(definition, "small")
    rows = results(tmp_path)
    assert len(rows) == 4                                       # 2 configurations x 1 task x 2 repetitions
    assert {r["configuration"] for r in rows} == {"codex-default", "claude-sonnet"}
    assert all(r["gates_passed"] and r["status"] == "done" and r["definition_hash"] for r in rows)
    assert [r["correctness"] for r in rows] == [1.0, 0.5, 1.0, 0.5]
    assert "codex-default: 2, 0.75, 0.50, 1.0000" in text and "claude-sonnet: 2, 0.75, 0.50, 0.1000" in text
    assert text.splitlines()[-1] == "recommended: claude-sonnet"             # tie on correctness: the cheaper one
    assert git(w.remote, "for-each-ref") == refs                              # nothing was pushed
    assert not list((tmp_path / "work" / "bench").glob("small/*/wt"))        # trial worktrees are gone
    judge_prompt = w.planner.calls[0].prompt
    assert "multiply(3, 4) == 12" in judge_prompt and "+def multiply" in judge_prompt and "- `partial`" in judge_prompt


def test_a_clearly_better_configuration_wins_even_if_it_costs_more(tmp_path):
    pricey, cheap = scripted(costly(1.0), costly(1.0)), scripted(costly(0.1), costly(0.1))
    w, s, *_ = bench_world(tmp_path, cheap, pricey, [PASS_JUDGE, PASS_JUDGE, PARTIAL_JUDGE, PARTIAL_JUDGE])
    bench, definition = runner(w, s, tmp_path)
    assert bench.run(definition, "small").splitlines()[-1] == "recommended: codex-default"


def test_only_one_configuration_can_be_chosen(tmp_path):
    pricey, cheap = scripted(costly(1.0), costly(1.0)), scripted(costly(0.1), costly(0.1))
    w, s, *_ = bench_world(tmp_path, cheap, pricey, [PASS_JUDGE, PASS_JUDGE])
    bench, definition = runner(w, s, tmp_path)
    bench.run(definition, "small", "claude-sonnet")
    assert {r["configuration"] for r in results(tmp_path)} == {"claude-sonnet"}
    with pytest.raises(KargahError):
        bench.run(definition, "small", "nope")
    with pytest.raises(KargahError):
        bench.run(definition, "missing")


def test_a_busy_lock_stops_the_benchmark(tmp_path):
    w, s, *_ = bench_world(tmp_path, scripted(), scripted(), [])
    bench, definition = runner(w, s, tmp_path)
    with RunLock(tmp_path / "work" / "state" / "run.lock") as held:
        assert held.acquired and bench.run(definition, "small") == "busy"


def test_a_build_that_changes_nothing_scores_zero_without_asking_a_judge(tmp_path):
    nothing = scripted(*[says("nothing to do")] * 4)       # 2 repetitions x (first try + one fix round)
    w, s, *_ = bench_world(tmp_path, scripted(), nothing, [])
    bench, definition = runner(w, s, tmp_path)
    bench.run(definition, "small", "codex-default")
    assert [(r["status"], r["correctness"], r["gates_passed"]) for r in results(tmp_path)] == [("failed", 0.0, False)] * 2
    assert w.planner.calls == []


def test_a_builder_limit_aborts_the_benchmark(tmp_path):
    limited = scripted(lambda r: HarnessResult(ok=False, limited=True))
    w, s, *_ = bench_world(tmp_path, scripted(), limited, [])
    bench, definition = runner(w, s, tmp_path)
    with pytest.raises(KargahError, match="usage limit"):
        bench.run(definition, "small", "codex-default")


def test_the_suite_scorers_grade_the_same_step_without_sampling(tmp_path):
    suite = SUITE.replace('scorers = ["task-compliance"]', 'scorers = ["task-compliance"]')
    builder = scripted(costly(0.1), costly(0.1))
    w, s, *_ = bench_world(tmp_path, builder, scripted(), [PASS_JUDGE, says("LABEL: partial\nREASON: x")] * 2, suite)
    bench, definition = runner(w, s, tmp_path)
    bench.run(definition, "small", "claude-sonnet")
    assert [r["scores"] for r in results(tmp_path)] == [{"task-compliance": 0.5}] * 2


def test_add_task_turns_a_recorded_step_into_a_todo_task_that_validate_rejects(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says("VERDICT: PASS")])
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    w.engine.tick()
    store = w.engine._s.runs
    repo = tmp_path / "checkout"
    path = add_task(store.steps(), store.artifact, "small", "r1-01", repo)
    assert path == repo / ".kargah/benchmarks/small/tasks/from-r1-01.toml"
    import tomllib
    data = tomllib.loads(path.read_text())
    assert data["success_criteria"] == "TODO" and data["start_sha"] == store.steps()[0].base_sha
    assert "add multiply(a, b)" in data["body"] and data["title"].startswith("#1 add multiply")
    (repo / ".kargah/benchmarks/small/suite.toml").write_text(SUITE.replace('scorers = ["task-compliance"]', "scorers = []"))
    assert any("still TODO" in p for p in load_definition(DirSource(repo)).problems)
    with pytest.raises(KargahError):
        add_task(store.steps(), store.artifact, "small", "r1-01", repo)           # not twice
    with pytest.raises(KargahError):
        add_task(store.steps(), store.artifact, "small", "nope", repo)
