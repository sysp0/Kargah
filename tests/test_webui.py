"""The read-only local UI: numbers come from the workdir's derived files, the server only answers GET."""
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest

from kargah.adapters.webui import make_server
from kargah.orchestrator.uidata import benchmarks, dashboard, improvements, runs, scorers

NOW = datetime(2026, 1, 10, 12, tzinfo=UTC)


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def step(sid, run, role, day, cost, seconds=10, status="ok"):
    return {"step_id": sid, "run": run, "ticket": 1, "role": role, "harness": "codex", "model": "", "status": status,
            "started": f"2026-01-{day:02d}T10:00:00+00:00", "seconds": seconds, "cost_usd": cost}


def score(sid, passed, day, scorer="task-compliance"):
    return {"scorer": scorer, "step_id": sid, "run": "r1", "ticket": 1, "role": "implement",
            "label": "compliant" if passed else "partial", "score": 1.0 if passed else 0.5, "passed": passed,
            "reason": f"why {sid}", "at": f"2026-01-{day:02d}T11:00:00+00:00"}


@pytest.fixture
def workdir(tmp_path):
    write(tmp_path / "steps.jsonl", [step("r1-01", "r1", "implement", 9, 0.5), step("r1-02", "r1", "review", 9, 0.25),
                                     step("r2-01", "r2", "implement", 10, 1.0), step("old-01", "r0", "review", 1, 9.0)])
    write(tmp_path / "log.jsonl", [
        {"kind": "run", "run": "r1", "ticket": 1, "outcome": "needs-human", "started": "2026-01-09T10:00:00+00:00",
         "seconds": 20, "cost_usd": 0.75, "steps": 2},
        {"kind": "run", "run": "r2", "ticket": 2, "outcome": "blocked", "started": "2026-01-10T10:00:00+00:00",
         "seconds": 10, "cost_usd": 1.0, "steps": 1},
        {"kind": "improvement", "issue": 7, "role": "implement", "score_keys": [["task-compliance", "r1-01"]]}])
    write(tmp_path / "scores.jsonl", [score("r1-01", True, 9), score("r2-01", False, 10), score("r1-01", False, 10)])
    (tmp_path / "bench").mkdir()
    write(tmp_path / "bench/results.jsonl", [
        {"suite": "small", "task": "power", "configuration": "a", "correctness": 1.0, "cost_usd": 0.4, "seconds": 50},
        {"suite": "small", "task": "power", "configuration": "b", "correctness": 1.0, "cost_usd": None, "seconds": 60}])
    return tmp_path


def test_dashboard_has_the_report_and_daily_series_inside_the_window(workdir):
    data = dashboard(workdir, "7d", NOW)
    assert data["cost_by_day"] == [{"day": "2026-01-09", "total": 0.75, "by_role": {"implement": 0.5, "review": 0.25}},
                                   {"day": "2026-01-10", "total": 1.0, "by_role": {"implement": 1.0}}]
    assert [d["day"] for d in data["runs_by_day"]] == ["2026-01-09", "2026-01-10"]
    assert data["runs_by_day"][1]["outcomes"] == {"blocked": 1} and "handoffs" in data["report"]


def test_runs_come_newest_first_with_their_steps(workdir):
    rows = runs(workdir, limit=10)
    assert [r["run"] for r in rows] == ["r2", "r1"]
    assert [s["role"] for s in rows[1]["steps"]] == ["implement", "review"] and rows[1]["steps"][0]["seconds"] == 10
    assert len(runs(workdir, limit=1)) == 1


def test_scorers_use_the_newest_record_of_each_step(workdir):
    [row] = scorers(workdir)
    assert (row["scorer"], row["count"], row["passed"]) == ("task-compliance", 2, 0)
    assert row["by_day"] == [{"day": "2026-01-10", "rate": 0.0, "count": 2}]
    assert [f["step_id"] for f in row["failures"]] == ["r1-01", "r2-01"] and row["failures"][0]["reason"] == "why r1-01"


def test_improvements_and_benchmarks(workdir):
    assert improvements(workdir) == [{"issue": 7, "role": "implement", "failures": 1}]
    [suite] = benchmarks(workdir)
    assert suite["suite"] == "small" and suite["recommended"] == "a"
    assert {s["configuration"] for s in suite["summaries"]} == {"a", "b"}


def test_an_empty_workdir_gives_empty_answers(tmp_path):
    assert runs(tmp_path) == [] and scorers(tmp_path) == [] and improvements(tmp_path) == [] and benchmarks(tmp_path) == []
    assert dashboard(tmp_path, "all", NOW)["cost_by_day"] == []


# ---- the server ----------------------------------------------------------------------------------------------
@pytest.fixture
def base(workdir):
    server = make_server(workdir, "127.0.0.1", 0, inbox=lambda: [{"kind": "Question", "number": 3}], issue_base="https://x/p")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url) as reply:
        return reply.status, reply.headers["Content-Type"], reply.read().decode()


def test_the_page_and_the_json_routes(base):
    status, kind, html = get(base + "/")
    assert status == 200 and kind.startswith("text/html") and "Kargah" in html
    assert json.loads(get(base + "/api/runs")[2])[0]["run"] == "r2"
    assert json.loads(get(base + "/api/inbox")[2]) == {"rows": [{"kind": "Question", "number": 3}], "available": True}
    assert json.loads(get(base + "/api/config")[2]) == {"issue_base": "https://x/p"}
    assert json.loads(get(base + "/api/dashboard?since=all")[2])["cost_by_day"][0]["day"] == "2026-01-01"


def test_bad_requests_are_refused(base):
    for url, code in ((base + "/nope", 404), (base + "/api/dashboard?since=banana", 400), (base + "/../etc/passwd", 404)):
        with pytest.raises(urllib.error.HTTPError) as error:
            get(url)
        assert error.value.code == code
    post = urllib.request.Request(base + "/api/runs", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(post)
    assert error.value.code == 405


def test_the_inbox_says_when_there_is_no_tracker(workdir):
    server = make_server(workdir, "127.0.0.1", 0, inbox=None, issue_base="")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/inbox"
        assert json.loads(get(url)[2]) == {"rows": [], "available": False}
    finally:
        server.shutdown()
        server.server_close()
