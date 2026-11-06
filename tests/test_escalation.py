"""When Codex is stuck, Claude gets exactly one extra round before the ticket is blocked (hard stop: a marker)."""
from engine_fixtures import SEED, make_world, multiply_feature, says, writes
from test_engine import MUST_FIX, PASS, labels

from kargah.domain.config import ProjectConfig
from kargah.domain.stages import Progress, Review, Stage, next_stage

CLAUDE = "claude-sonnet-5-5"
TIGHT = {".kargah/config.toml": SEED[".kargah/config.toml"] + "[limits]\nmax_fix_rounds = 1\nmax_rework = 1\n"}
LAZY = writes({"tests/test_lazy.py": "def test_x():\n    assert 1 == 1\n"})


def edit(i):
    return writes({"src/calc/ops.py": "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n"
                                      f"\n# {i}\n"})


def escalations(world, n=1):
    return sum("kargah:escalated" in c.body for c in world.tracker.comments(n))


def test_the_default_caps_are_loose():
    assert (ProjectConfig().max_fix_rounds, ProjectConfig().max_rework) == (2, 3)


def test_one_more_rework_round_is_allowed_after_an_escalation():
    failed = tuple(Review("h", 1) for _ in range(3))
    base = dict(has_work=True, head_sha="h", head_complete=True, reviews=failed, has_build=True)
    assert next_stage(Progress(**base), 2) is Stage.BLOCKED
    assert next_stage(Progress(**base, escalated=True), 2) is Stage.REWORK
    assert next_stage(Progress(**{**base, "reviews": failed + (Review("h", 1),)}, escalated=True), 2) is Stage.BLOCKED


def test_claude_takes_over_when_the_reviewer_still_objects_after_the_rework_rounds(tmp_path):
    w = make_world(tmp_path, [multiply_feature(), edit(1), edit(2)], [says(MUST_FIX), says(MUST_FIX), says(PASS)],
                   TIGHT)
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "needs-human"
    assert [c.model for c in w.builder.calls][-1] == CLAUDE and CLAUDE not in [c.model for c in w.builder.calls][:-1]
    assert escalations(w) == 1


def test_claude_takes_over_when_the_gates_keep_failing(tmp_path):
    w = make_world(tmp_path, [LAZY, LAZY, multiply_feature()], [says(PASS)], TIGHT)
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "needs-human"
    assert w.builder.calls[2].model == CLAUDE and w.builder.calls[1].model != CLAUDE
    assert escalations(w) == 1


def test_if_claude_fails_too_the_ticket_is_blocked_and_nothing_loops(tmp_path):
    w = make_world(tmp_path, [multiply_feature(), edit(1), edit(2)] + [edit(i) for i in range(3, 9)],
                   [says(MUST_FIX)] * 8, TIGHT)
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "blocked" and "blocked" in labels(w)
    assert len(w.builder.calls) == 3 and escalations(w) == 1
    assert w.engine.tick() == "idle" and len(w.builder.calls) == 3


def test_a_failed_claude_build_after_the_help_is_blocked(tmp_path):
    w = make_world(tmp_path, [LAZY, LAZY, LAZY, LAZY, LAZY], [], TIGHT)
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "blocked"
    assert len(w.builder.calls) == 4 and escalations(w) == 1       # 2 Codex rounds, then 2 Claude rounds, then stop


def test_no_escalation_when_claude_already_builds_the_ticket(tmp_path):
    w = make_world(tmp_path, [LAZY, LAZY, multiply_feature()], [], TIGHT)
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready", "builder-claude"))
    assert w.engine.tick() == "blocked"
    assert len(w.builder.calls) == 2 and escalations(w) == 0
