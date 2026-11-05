from pathlib import Path
import json

from devchain import config, events
from devchain.model import View
from devchain.usage import Usage, from_claude_result, from_codex_event


def test_events_append_and_read_in_order(tmp_path):
    run = events.create(tmp_path, "feature")
    run.emit("a", n=1)
    run.emit("b", n=2)
    with run.events_path.open("a") as fh:
        fh.write('{"type": "half"')  # a line still being written
    found, offset = events.read(run.events_path)
    assert [e["type"] for e in found] == ["a", "b"]
    with run.events_path.open("a") as fh:
        fh.write(', "n": 3}\n')
    more, _ = events.read(run.events_path, offset)
    assert [e["type"] for e in more] == ["half"]


def test_list_runs_and_latest(tmp_path):
    first = events.create(tmp_path, "feature")
    first.emit("run_started")
    second = events.create(tmp_path, "qa")
    second.emit("run_started")
    assert [r.id for r in events.list_runs(tmp_path)] == [first.id, second.id]
    assert events.open_run(tmp_path, None).id == second.id


def test_missing_config_is_a_clear_error(tmp_path):
    try:
        config.load(tmp_path)
    except config.ConfigError as exc:
        assert "devchain.toml" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_codex_usage_counts_cached_separately():
    u = from_codex_event({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 800,
                                                               "output_tokens": 5, "new_field": 1}})
    assert (u.input, u.cached, u.output) == (200, 800, 5)
    assert round(u.cache_pct) == 80
    assert from_codex_event({"type": "item.completed"}) is None


def test_claude_usage_and_cost():
    u = from_claude_result({"type": "result", "total_cost_usd": 0.5,
                            "usage": {"input_tokens": 10, "cache_read_input_tokens": 80,
                                      "cache_creation_input_tokens": 10, "output_tokens": 3}})
    assert (u.input, u.cached, u.cache_write, u.output, u.calls) == (10, 80, 10, 3, 1)
    assert u.cost_usd == 0.5 and round(u.cache_pct) == 80
    total = Usage().add(u).add(u)
    assert total.calls == 2 and total.cost_usd == 1.0


def test_view_folds_events():
    view = View(run_id="r")
    for e in [
        {"ts": 1, "type": "run_started", "kind": "feature", "stage": "s", "packages": ["P1", "P2"]},
        {"ts": 2, "type": "pkg", "pkg": "P1", "state": "codex", "round": 0},
        {"ts": 3, "type": "usage", "pkg": "P1", "agent": "codex", "input": 5, "cached": 5, "calls": 1},
        {"ts": 4, "type": "usage", "pkg": "P1", "agent": "claude", "input": 1, "cost_usd": 0.2, "calls": 1},
        {"ts": 5, "type": "pkg", "pkg": "P1", "state": "done", "round": 0, "commit": "abc"},
        {"ts": 6, "type": "run_finished", "outcome": "done"},
    ]:
        view.apply(e)
    assert view.order == ["P1", "P2"]
    assert view.packages["P1"].state == "done" and view.packages["P1"].commit == "abc"
    assert view.packages["P2"].state == "waiting"
    assert view.totals["codex"].cached == 5 and view.totals["claude"].cost_usd == 0.2
    assert view.packages["P1"].elapsed() == 3
    assert view.live_seq == 2 and len(view.live_since(1)) == 1
    assert json.dumps(view.totals["codex"].as_dict())


def test_live_lines_drop_terminal_escapes(tmp_path):
    from devchain import events as ev
    from devchain.agents import Live

    run = ev.create(tmp_path, "qa")
    Live(run, "S1", "playwright").line("\x1b[1A\x1b[2K[1/1] \x1b[32mpassed\x1b[0m\x07", force=True)
    found, _ = ev.read(run.events_path)
    assert [e["text"] for e in found if e["type"] == "live"] == ["[1/1] passed"]


def test_loop_settings_in_the_repo_config():
    cfg = config.load(Path(__file__).resolve().parents[2])
    assert cfg.get("loop.poll_seconds") == 300
    assert cfg.get("qa_worktree.env.QA_UI_PORT") == "5193"
    assert cfg.get("qa.fix_max_files") is None and cfg.get("feature.gate") is None
