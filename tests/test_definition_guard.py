"""The factory definition (.kargah/) comes from the default branch; a build may change it only when asked to."""
from engine_fixtures import EXPORT, MULTIPLY_CODE, MULTIPLY_TEST, make_world, says, writes

PASS = "VERDICT: PASS"


def feature_with_config(config: str, text: str = "done"):
    return writes({"tests/test_multiply.py": MULTIPLY_TEST, "src/calc/ops.py": MULTIPLY_CODE,
                   "src/calc/__init__.py": EXPORT, ".kargah/config.toml": config}, text)


def test_a_build_may_not_change_the_definition(tmp_path):
    w = make_world(tmp_path, [feature_with_config('[check]\ncommand = "true"\n'), says("done")], [])
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "blocked"
    assert "factory-change" in w.builder.calls[1].prompt


def test_the_definition_is_read_from_the_default_branch_not_the_ticket_branch(tmp_path):
    # the edit is allowed (factory-change) and committed as WIP; the next run must still use the default check
    first = feature_with_config('[check]\ncommand = "false"\n', "QUESTION: is this ok?")
    touch = writes({"src/calc/ops.py": MULTIPLY_CODE + "\n# reviewed\n"})
    w = make_world(tmp_path, [first, touch, touch], [says(PASS)])
    n = w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready", "factory-change"))
    assert w.engine.tick() == "question"
    w.tracker.human_says(n, "yes")
    assert w.engine.tick() == "needs-human"
