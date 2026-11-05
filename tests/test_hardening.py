import time

import pytest
from conftest import git
from helpers import FIX, PASS, feature, setup, work

from kargah import agents, config, events, stats, wip


def test_a_step_that_goes_silent_is_killed_at_its_timeout(repo, tmp_path):
    cfg = config.load(repo.root)
    run = events.create(cfg.runs_dir, "x")
    start = time.time()
    res = agents.shell(cfg, run, None, "hang", "sleep 30", tmp_path / "hang.log", timeout=1)
    assert res.rc == 124 and time.time() - start < 10
    assert "timed out" in (tmp_path / "hang.log").read_text()


def test_wip_keeps_the_work_on_disk_before_cleaning_and_not_when_it_cannot_be_written(repo, monkeypatch):
    (repo.root / "a.txt").write_text("work")
    store = wip.Wip(repo.root, repo.root / ".devchain/wip/x")
    assert store.save("P1", "s1", "stopped") == ["a.txt"]
    assert "work" in (repo.root / ".devchain/wip/x/P1/work.patch").read_text() and not (repo.root / "a.txt").exists()
    (repo.root / "b.txt").write_text("more")
    monkeypatch.setattr(wip, "write_atomic", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        store.save("P2", "", "stopped")
    assert (repo.root / "b.txt").read_text() == "more"   # the tree still has the work


def test_a_file_outside_the_row_goes_back_to_codex_before_the_review(repo):
    setup(repo)
    repo.codex({"write": {**work("a")["write"], "src/other.py": "y = 2\n"}},
               {"delete": ["src/other.py"]})
    repo.claude(PASS)
    f = feature(repo)
    assert f.package("P1") == "done"
    assert "src/other.py" in repo.prompt("codex", 1)
    assert repo.calls("claude") == 1   # the first round never reached the review


def test_stats_reads_rounds_failed_checks_and_cost_from_the_runs(repo):
    setup(repo)
    repo.codex(work("a"), work("a"))
    repo.claude(FIX, PASS)
    assert feature(repo).package("P1") == "done"
    text = stats.report(config.load(repo.root))
    assert "P1" in text and "review" in text
