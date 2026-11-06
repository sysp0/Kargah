import json
from datetime import UTC, datetime, timedelta

from memory_tracker import MemoryTracker

from kargah.domain.inbox import first_line
from kargah.domain.markers import bot_comment
from kargah.domain.metrics import compute
from kargah.orchestrator.inbox import collect_inbox, format_row

NOW = datetime(2026, 2, 1, tzinfo=UTC)


def at(days_ago, hours=0):
    return (NOW - timedelta(days=days_ago, hours=hours)).isoformat()


def run(ticket, outcome, days_ago=1):
    return {"kind": "run", "ticket": ticket, "outcome": outcome, "started": at(days_ago)}


def completion(ticket, merged_days_ago=1, pushed=False, interactions=2, review_hours=None, outcome="merged",
               labels=()):
    merged = NOW - timedelta(days=merged_days_ago)
    return {"kind": "completion", "ticket": ticket, "outcome": outcome, "labels": list(labels),
            "kickoff_at": (merged - timedelta(hours=10)).isoformat(), "handoff_at": (merged - timedelta(hours=6)).isoformat(),
            "first_human_review_at": (merged - timedelta(hours=review_hours)).isoformat() if review_hours else None,
            "merged_at": merged.isoformat() if outcome == "merged" else None, "human_interactions": interactions,
            "human_pushed": pushed}


def step(ticket, role, cost, days_ago=1, step_id="s"):
    return {"step_id": f"{step_id}-{role}", "ticket": ticket, "role": role, "cost_usd": cost, "started": at(days_ago)}


RUNS = [run(1, "needs-human"), run(2, "needs-human"), run(2, "needs-human"), run(3, "blocked"), run(4, "needs-human", 30)]
COMPLETIONS = [completion(1, review_hours=4, interactions=2), completion(2, pushed=True, interactions=6),
               completion(9, 20)]
STEPS = [step(1, "implement", 0.5), step(1, "review", 0.1), step(2, "implement", None), step(2, "review", 0.3),
         step(3, "implement", 1.0), step(9, "implement", 0.2, 40)]


def report(since_days=7):
    return compute(RUNS, COMPLETIONS, STEPS, [], NOW - timedelta(days=since_days), NOW)


def test_counts_in_the_window():
    r = report()
    assert r["runs"] == {"needs-human": 3, "blocked": 1}
    assert r["steps_by_role"] == {"implement": 3, "review": 2}
    assert (r["handoffs"], r["merged"], r["merge_rate"]) == (2, 2, 1.0)           # ticket 4 is outside the window
    assert r["autonomy"] == 0.5
    assert r["human_interactions_per_mr"] == {"mean": 4, "median": 4}


def test_cycle_times_are_medians_in_seconds_and_skip_missing_reviews():
    cycle = report()["cycle"]
    assert cycle["kickoff_to_handoff"] == 4 * 3600 and cycle["kickoff_to_merge"] == 10 * 3600
    assert cycle["handoff_to_first_review"] == 2 * 3600 and cycle["first_review_to_merge"] == 4 * 3600


def test_costs():
    r = report()
    assert r["cost_per_mr"] == {"median": 0.45, "steps_unknown_cost": 1}      # ticket 1: 0.6, ticket 2: 0.3 (one unknown)
    assert r["cost_by_role"] == {"implement": 1.5, "review": 0.4}


def test_no_merge_gives_null_not_an_error():
    r = compute([run(1, "blocked")], [], [], [], None, NOW)
    assert (r["merge_rate"], r["autonomy"], r["cycle"]["kickoff_to_merge"], r["cost_per_mr"]["median"]) == \
        (None, None, None, None)
    assert r["human_interactions_per_mr"] == {"mean": None, "median": None}
    json.dumps(r)


def test_scorers_use_the_latest_record_per_step_and_improvements_count_factory_changes():
    scores = [{"scorer": "q", "step_id": "a", "label": "bad", "passed": False},
              {"scorer": "q", "step_id": "a", "label": "good", "passed": True},
              {"scorer": "q", "step_id": "b", "label": "bad", "passed": False}]
    done = [completion(5, labels=["factory-change"]), completion(6, outcome="cancelled", labels=["factory-change"])]
    done[1]["kickoff_at"] = at(2)
    r = compute([], done, [], scores, None, NOW)
    assert r["scorers"] == {"q": {"count": 2, "pass_rate": 0.5, "labels": {"good": 1, "bad": 1}}}
    assert r["improvement_acceptance"] == 0.5


def test_inbox_is_oldest_first_with_the_first_line_of_the_last_bot_comment():
    tracker = MemoryTracker()
    a = tracker.open_ticket("old question", labels=("needs-info",))
    b = tracker.open_ticket("review me", labels=("needs-human",))
    tracker.open_ticket("not waiting", labels=("in-progress",))
    tracker.post_comment(a, bot_comment("question", "r1", "I need an answer:\n\n> which column?"))
    tracker.post_comment(b, bot_comment("ready", "r2", "Ready for your review: https://x/mr/1\n\nmore"))
    now = datetime(2026, 1, 1, 3, tzinfo=UTC)
    rows = collect_inbox(tracker, now)
    assert [(r.kind, r.number) for r in rows] == [("Question", a), ("MR review", b)]
    assert rows[0].summary == "I need an answer:" and rows[1].summary.startswith("Ready for your review")
    assert rows[0].waiting_seconds > rows[1].waiting_seconds
    assert "[Question] #1 old question (waiting 2h59m)" in format_row(rows[0])


def test_first_line_skips_header_and_marker():
    assert first_line(bot_comment("blocked", "r", "Why: x")) == "Why: x"
    assert first_line("") == ""


def test_report_command_reads_the_workdir_and_prints_one_number_per_line(tmp_path, capsys):
    from kargah.orchestrator.cli import main
    (tmp_path / "log.jsonl").write_text("\n".join(json.dumps(r) for r in [run(1, "needs-human", 0), {**run(2, "x")},
                                                                         completion(1, 0)]) + "\nnot json\n")
    (tmp_path / "steps.jsonl").write_text(json.dumps(step(1, "implement", 0.5, 0)) + "\n")
    assert main(["report", "--workdir", str(tmp_path), "--since", "all"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "handoffs: 1" in out and "merged: 1" in out and "cost_by_role.implement: 0.5" in out
    assert main(["report", "--workdir", str(tmp_path), "--since", "all", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["merged"] == 1
    assert main(["report", "--workdir", str(tmp_path / "empty")]) == 0         # no files: all zero, no crash
    assert main(["report", "--workdir", str(tmp_path), "--since", "soon"]) == 2


def test_inbox_command_needs_the_gitlab_settings(monkeypatch, capsys):
    from kargah.orchestrator.cli import main
    for key in ("KARGAH_GITLAB_URL", "KARGAH_GITLAB_PROJECT", "KARGAH_GITLAB_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    assert main(["inbox"]) == 2 and "KARGAH_GITLAB" in capsys.readouterr().err
