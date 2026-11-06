"""Phase 9: cron automations only create issues; the normal pipeline does the work. Never `ready`."""
import pytest
from engine_fixtures import make_world
from memory_tracker import MemoryTracker

from kargah.errors import KargahError
from kargah.orchestrator.factory_issue import create_factory_issue


def raw(front: str, body: str = "Check the dependencies and list what is outdated.") -> dict[str, str]:
    return {".kargah/automations/audit/automation.md": f"+++\n{front}+++\n{body}\n"}


def automation(extra: str = "") -> dict[str, str]:
    return raw('enabled = true\ncron = "0 9 * * *"\ntitle = "Dependency audit {date}"\n' + extra)


def _sub(tmp_path, name):
    (tmp_path / name).mkdir()
    return tmp_path / name


def auto_issues(world):
    return world.tracker.tickets_with_label("kargah-auto", include_closed=True)


def test_a_due_slot_creates_one_issue_without_ready_and_never_runs_an_agent(tmp_path):
    w = make_world(tmp_path, [], [], automation())
    assert w.engine.tick() == "idle"
    [issue] = auto_issues(w)
    assert issue.labels == {"kargah-auto"} and issue.title == "Dependency audit 2026-01-01"
    assert "Check the dependencies" in issue.body and "kargah:automation name=audit slot=2026-01-01T09:00" in issue.body
    assert w.builder.calls == [] and w.planner.calls == [] and w.reviewer.calls == []


def test_the_same_slot_is_not_created_twice_even_when_the_issue_is_closed(tmp_path):
    w = make_world(tmp_path, [], [], automation())
    w.engine.tick()
    w.tracker.close_ticket(auto_issues(w)[0].number)
    w.engine.tick()
    assert len(auto_issues(w)) == 1


def test_after_a_long_stop_only_the_newest_missed_slot_is_created(tmp_path):
    w = make_world(tmp_path, [], [], automation())
    w.engine.tick()
    w.clock.advance(days=4)                     # slots of day 2, 3, 4 and 5 were missed
    w.engine.tick()
    assert [t.title for t in auto_issues(w)] == ["Dependency audit 2026-01-01", "Dependency audit 2026-01-05"]


def test_extra_labels_are_added_but_ready_is_refused(tmp_path):
    w = make_world(tmp_path, [], [], automation('labels = ["audit"]\n'))
    w.engine.tick()
    assert auto_issues(w)[0].labels == {"kargah-auto", "audit"}
    bad = make_world(_sub(tmp_path, "bad"), [], [], automation('labels = ["ready"]\n'))
    assert bad.engine.tick().startswith("config-error") and auto_issues(bad) == []


def test_disabled_and_invalid_automations(tmp_path):
    off = make_world(_sub(tmp_path, "off"), [], [], raw('enabled = false\ncron = "0 9 * * *"\ntitle = "t"\n'))
    assert off.engine.tick() == "idle" and auto_issues(off) == []
    broken = make_world(_sub(tmp_path, "broken"), [], [], raw('enabled = true\ncron = "61 9 * * *"\ntitle = "t"\n'))
    result = broken.engine.tick()
    assert result.startswith("config-error") and "cron" in result


def test_no_slot_in_the_last_week_means_no_issue(tmp_path):
    w = make_world(tmp_path, [], [], raw('enabled = true\ncron = "0 0 1 6 *"\ntitle = "t"\n'))
    assert w.engine.tick() == "idle" and auto_issues(w) == []


def test_the_factory_never_creates_a_ready_issue():
    tracker = MemoryTracker()
    with pytest.raises(KargahError, match="ready"):
        create_factory_issue(tracker, "t", "b", ("kargah-auto", "ready"))
    number = create_factory_issue(tracker, "t", "b", ("factory-change",))
    assert tracker.get_ticket(number).labels == {"factory-change"}
