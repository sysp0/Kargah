"""Phase 7: the factory proposes improvements of its own agents as issues; the owner activates them."""
import json
from datetime import UTC, datetime, timedelta

from engine_fixtures import SEED, make_world, multiply_feature, says, writes
from test_engine import PASS

from kargah.adapters.fs_scores import FsScoreStore
from kargah.adapters.toml_config import parse_project_config
from kargah.domain.improvement import due, failures, issue_text, open_roles

NOW = datetime(2026, 1, 10, tzinfo=UTC)
OWN = {"task-compliance"}


def record(step, *, scorer="task-compliance", role="implement", passed=False, label="no", at=NOW, ticket=1):
    return {"scorer": scorer, "step_id": step, "run": "r", "ticket": ticket, "role": role, "label": label,
            "score": 1.0 if passed else 0.0, "passed": passed, "reason": f"why {step}", "at": at.isoformat()}


def test_the_latest_record_of_a_step_decides_and_only_own_scorers_count():
    rows = [record("s1"), record("s1", passed=True), record("s2"), record("s3", scorer="other"),
            record("s4", label=None), record("s5")]
    rows[4]["label"] = None
    assert [f.step_id for f in failures(rows, OWN, claimed={("task-compliance", "s5")})] == ["s2"]


def test_the_count_threshold_and_the_age_threshold():
    four = failures([record(f"s{i}") for i in range(4)], OWN, set())
    assert not due(four, threshold=5, max_age_days=7, now=NOW)
    assert due(four, threshold=4, max_age_days=7, now=NOW)
    old = failures([record("s1", at=NOW - timedelta(days=7))], OWN, set())
    assert due(old, threshold=5, max_age_days=7, now=NOW)
    young = failures([record("s1", at=NOW - timedelta(days=6))], OWN, set())
    assert not due(young, threshold=5, max_age_days=7, now=NOW)
    assert not due([], threshold=1, max_age_days=0, now=NOW)


def test_the_issue_text_is_bounded_and_scoped_to_the_definition():
    found = failures([record(f"s{i}", ticket=i) for i in range(12)], OWN, set())
    title, body = issue_text("implement", found)
    assert title == "Factory: improve the implement agent (12 failed scores)"
    assert "<!-- kargah:improvement role=implement -->" in body
    assert body.count("why s") == 10 and "task-compliance: no=12" in body and "Change only files under `.kargah/`" in body
    assert open_roles(["x\n<!-- kargah:improvement role=implement -->"]) == {"implement"}


def test_config_keys():
    cfg = parse_project_config("[self_improvement]\nenabled = true\nfailed_threshold = 2\nmax_age_days = 3\n"
                               "[proof]\nexempt_paths = [\"docs/\"]\n")
    assert (cfg.self_improvement, cfg.improvement_failed_threshold, cfg.improvement_max_age_days,
            cfg.proof_exempt_paths) == (True, 2, 3, ("docs/",))
    default = parse_project_config(None)
    assert (default.self_improvement, default.improvement_failed_threshold, default.improvement_max_age_days,
            default.proof_exempt_paths) == (False, 5, 7, (".kargah/", "docs/"))


# ---- the engine ------------------------------------------------------------------------------------------
ON = {".kargah/config.toml": SEED[".kargah/config.toml"] + "[self_improvement]\nenabled = true\nfailed_threshold = 2\n"}


def fail(world, *steps, role="implement"):
    store = FsScoreStore(world.workdir)
    for step in steps:
        store.add(record(step, role=role, at=world.clock.now))


def factory_issues(world, include_closed=False):
    return world.tracker.tickets_with_label("factory-change", include_closed=include_closed)


def claims(world):
    rows = [json.loads(x) for x in world.log()]
    return [r for r in rows if r.get("kind") == "improvement"]


def test_it_is_off_by_default(tmp_path):
    w = make_world(tmp_path, [], [])
    fail(w, "a", "b", "c", "d", "e", "f")
    assert w.engine.tick() == "idle" and factory_issues(w) == []


def test_an_issue_is_created_without_ready_and_not_twice(tmp_path):
    w = make_world(tmp_path, [], [], ON)
    fail(w, "a")
    assert w.engine.tick() == "idle" and factory_issues(w) == []          # below the threshold
    fail(w, "b")
    assert w.engine.tick() == "idle"
    [issue] = factory_issues(w)
    assert issue.labels == {"factory-change"} and "ready" not in issue.labels
    assert issue.title == "Factory: improve the implement agent (2 failed scores)"
    assert w.engine.tick() == "idle" and len(factory_issues(w)) == 1       # an open issue for the role exists
    [claim] = claims(w)
    assert claim["issue"] == issue.number and claim["role"] == "implement" and len(claim["score_keys"]) == 2


def test_claimed_failures_are_not_counted_again_but_new_ones_are(tmp_path):
    w = make_world(tmp_path, [], [], ON)
    fail(w, "a", "b")
    w.engine.tick()
    [issue] = factory_issues(w)
    w.tracker.close_ticket(issue.number)
    assert w.engine.tick() == "idle" and len(factory_issues(w, include_closed=True)) == 1
    fail(w, "c", "d")
    w.engine.tick()
    assert len(factory_issues(w, include_closed=True)) == 2


def test_each_role_gets_its_own_issue(tmp_path):
    w = make_world(tmp_path, [], [], ON)
    fail(w, "a", "b")
    fail(w, "c", "d", role="review")
    w.engine.tick()
    assert sorted(t.title.split()[3] for t in factory_issues(w)) == ["implement", "review"]


# ---- a change that touches only config needs no proof --------------------------------------------------
def test_a_definition_only_change_needs_no_new_test(tmp_path):
    only_config = writes({".kargah/skills/style/SKILL.md": "---\nname: style\ndescription: x\n---\nbe brief\n"})
    w = make_world(tmp_path, [only_config], [says(PASS)])
    w.tracker.open_ticket("improve", "tighten the skill", ("ready", "factory-change"))
    assert w.engine.tick() == "needs-human"


def test_a_source_change_without_a_test_is_still_refused(tmp_path):
    no_test = writes({"src/calc/extra.py": "X = 1\n"})
    w = make_world(tmp_path, [no_test] * 6, [])
    w.tracker.open_ticket("improve", "add a constant", ("ready", "factory-change"))
    assert w.engine.tick() == "blocked"


def test_the_normal_path_still_runs_the_proof(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "needs-human"
