from engine_fixtures import SEED, make_world, multiply_feature, says

from kargah.orchestrator.cli import main

BROKEN = SEED[".kargah/config.toml"] + '[models]\nbuild = "x"\n'


def test_validate_prints_ok_for_a_good_folder(tmp_path, capsys):
    (tmp_path / ".kargah").mkdir()
    (tmp_path / ".kargah/config.toml").write_text(SEED[".kargah/config.toml"])
    assert main(["validate", "--repo", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_validate_lists_every_problem_and_exits_1(tmp_path, capsys):
    (tmp_path / ".kargah/agents/review").mkdir(parents=True)
    (tmp_path / ".kargah/config.toml").write_text(BROKEN)
    (tmp_path / ".kargah/agents/review/agent.md").write_text('+++\nmodle = "x"\n+++\n')
    assert main(["validate", "--repo", str(tmp_path)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and lines[0].startswith(".kargah/config.toml:") and "unknown key 'modle'" in lines[1]


def test_a_broken_default_branch_definition_stops_the_engine_before_touching_any_ticket(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says("VERDICT: PASS")], files={".kargah/config.toml": BROKEN})
    n = w.tracker.open_ticket("add multiply", "x", ("ready",))
    outcome = w.engine.tick()
    assert outcome.startswith("config-error: .kargah/config.toml: [models] moved to")
    assert w.tracker.get_ticket(n).labels == {"ready"} and w.tracker.comments(n) == []
    assert w.builder.calls == [] and w.log() == []


def test_watch_waits_between_polls_while_the_definition_is_broken(tmp_path, monkeypatch):
    w = make_world(tmp_path, [], [], files={".kargah/config.toml": BROKEN})
    sleeps, stops = [], iter([False, False, True])
    monkeypatch.setattr("kargah.orchestrator.engine.time.sleep", sleeps.append)
    seen = []
    w.engine.watch(5.0, lambda: next(stops), seen.append)
    assert len(seen) == 2 and sleeps == [5.0, 5.0]
