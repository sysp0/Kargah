"""Triage, spec and the approval gate through the engine (plan phase 4)."""
import json

from engine_fixtures import SEED, make_world, multiply_feature, says, writes
from test_lifecycle import markers

from kargah.domain.triage import parse_triage

PASS = "VERDICT: PASS"
AUTO = SEED[".kargah/config.toml"].replace('triage = "never"', 'triage = "auto"').replace('spec = "never"', 'spec = "auto"')
FILES = {".kargah/config.toml": AUTO}
SPEC_FILE = "docs/specs/1.md"


def report(size="M", ambiguity="none", extra=""):
    return says(f"SIZE: {size}\nAMBIGUITY: {ambiguity}\nACCEPTANCE: multiply(3, 4) == 12\nREFERENCE: src/calc/ops.py:1\n{extra}")


def spec(text="# Spec\n"):
    return writes({SPEC_FILE: text}, f"SPEC: {SPEC_FILE}")


def second_world(tmp_path, *args, **kw):
    (tmp_path / "b").mkdir()
    return make_world(tmp_path / "b", *args, **kw)


def labels(w, n=1):
    return set(w.tracker.get_ticket(n).labels)


def ticket(w, body="add multiply(a, b)"):
    return w.tracker.open_ticket("add multiply", body, ("ready",))


def test_a_ticket_without_acceptance_is_triaged_and_the_build_gets_the_criteria(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES, [report("M")])
    ticket(w)
    assert w.engine.tick() == "needs-human"
    [comment] = markers(w, "triage")
    assert parse_triage(comment.body).size == "M" and "size=M ambiguous=0" in comment.body
    assert "## Acceptance criteria (from triage)" in w.builder.calls[0].prompt
    assert "multiply(3, 4) == 12" in w.builder.calls[0].prompt and "src/calc/ops.py:1" in w.builder.calls[0].prompt
    assert w.tracker.get_ticket(1).body == "add multiply(a, b)"          # the owner's issue is never edited


def test_a_ticket_with_an_acceptance_section_skips_triage(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES, [])
    ticket(w, "add multiply\n\n## Acceptance criteria\n- multiply(3, 4) == 12")
    assert w.engine.tick() == "needs-human" and w.planner.calls == []


def test_triage_questions_ask_the_owner_and_triage_runs_again_after_the_answer(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES,
                   [says("QUESTION: ints or floats?\nQUESTION: negative numbers?"), report("S")])
    n = ticket(w)
    assert w.engine.tick() == "question" and labels(w) == {"needs-info"}
    assert "> ints or floats?" in markers(w, "question")[0].body and "> negative numbers?" in markers(w, "question")[0].body
    w.tracker.human_says(n, "floats, and yes")
    assert w.engine.tick() == "needs-human"
    assert "floats, and yes" in w.planner.calls[1].prompt


def test_an_invalid_triage_reply_is_asked_again_once_then_blocks(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES, [says("looks big"), report("S")])
    ticket(w)
    assert w.engine.tick() == "needs-human"
    assert "did not follow the format" in w.planner.calls[1].prompt
    w2 = second_world(tmp_path, [], [], FILES, [says("no"), says("still no")])
    ticket(w2)
    assert w2.engine.tick() == "blocked"


def test_a_large_ticket_gets_a_spec_waits_for_changes_and_approval_then_builds_from_it(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES,
                   [report("L"), spec("# Spec v1\n"), spec("# Spec v2\n")])
    n = ticket(w)
    assert w.engine.tick() == "awaiting-approval" and labels(w) == {"needs-approval"}
    assert "Spec ready:" in markers(w, "spec")[0].body and "label `approved`" in markers(w, "spec")[0].body
    log = w.remote_log("kargah/1")
    assert "Kargah-Task: spec" in log and "Kargah-State: complete" in log and "kargah/1" in w.host.drafts
    assert w.engine.tick() == "idle"                                   # nobody answered
    w.tracker.human_says(n, "please add an out-of-scope section")
    assert w.engine.tick() == "awaiting-approval" and len(markers(w, "spec")) == 2
    assert "out-of-scope" in w.planner.calls[2].prompt
    w.tracker.human_says(n, "/approve")
    assert w.engine.tick() == "needs-human"
    assert "docs/specs/1.md" in w.builder.calls[0].prompt and "Validation criteria" in w.builder.calls[0].prompt
    assert len(w.planner.calls) == 3                                   # triage + two specs, nothing more


def test_ambiguity_alone_asks_for_a_spec(tmp_path):
    w = make_world(tmp_path, [], [], FILES, [report("S", "floats or ints?"), spec()])
    ticket(w)
    assert w.engine.tick() == "awaiting-approval"


def test_the_spec_agent_may_change_only_the_spec_file(tmp_path):
    other = writes({SPEC_FILE: "x", "src/calc/ops.py": "oops"}, "SPEC")
    fixed = writes({SPEC_FILE: "x", "src/calc/ops.py": SEED["src/calc/ops.py"]}, "SPEC")     # undoes the stray edit
    w = make_world(tmp_path, [], [], FILES, [report("L"), other, fixed])
    ticket(w)
    assert w.engine.tick() == "awaiting-approval"
    assert "Change only `docs/specs/1.md`" in w.planner.calls[2].prompt
    w2 = second_world(tmp_path, [], [], FILES, [report("L"), other, other])
    ticket(w2)
    assert w2.engine.tick() == "blocked"


def test_a_comment_that_is_not_approve_is_a_change_request(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES, [report("L"), spec(), spec("# v2\n")])
    n = ticket(w)
    w.engine.tick()
    w.tracker.human_says(n, "looks fine to me")
    assert w.engine.tick() == "awaiting-approval" and len(w.planner.calls) == 3


def test_the_model_follows_the_ticket_size_and_is_recorded(tmp_path):
    agent = '+++\nmodels_by_size = { S = "small-model", L = "big-model" }\n+++\n'
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], {**FILES, ".kargah/agents/implement/agent.md": agent},
                   [report("S")])
    ticket(w)
    assert w.engine.tick() == "needs-human"
    assert w.builder.calls[0].model == "small-model"
    steps = [json.loads(line) for line in (tmp_path / "work" / "steps.jsonl").read_text().splitlines()]
    assert [(s["role"], s["model"]) for s in steps] == [("triage", "claude-sonnet-5-5"), ("implement", "small-model"),
                                                        ("review", "claude-sonnet-5-5")]


def test_a_size_without_a_mapping_uses_the_default_model(tmp_path):
    agent = '+++\nmodel = "default-model"\nmodels_by_size = { XS = "tiny" }\n+++\n'
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], {**FILES, ".kargah/agents/implement/agent.md": agent},
                   [report("M")])
    ticket(w)
    w.engine.tick()
    assert w.builder.calls[0].model == "default-model"


def test_the_limit_of_the_triage_agent_waits_like_any_other_limit(tmp_path):
    from kargah.ports.harness import HarnessResult
    w = make_world(tmp_path, [], [], FILES, [lambda r: HarnessResult(ok=False, limited=True)])
    ticket(w)
    assert w.engine.tick() == "limit-unknown" and "blocked" in labels(w)


def test_a_run_that_dies_after_the_triage_question_does_not_ask_it_twice(tmp_path):
    ask = says("QUESTION: ints or floats?")
    w = make_world(tmp_path, [], [], FILES, [ask, ask])
    original, state = w.tracker.add_label, {"failed": False}

    def flaky(number, label):
        if label == "needs-info" and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("network down")
        original(number, label)

    w.tracker.add_label = flaky
    ticket(w)
    try:
        w.engine.tick()
    except RuntimeError:
        pass
    assert w.engine.tick() == "question"
    assert len(markers(w, "question")) == 1


def test_the_approved_label_starts_the_build_without_any_comment(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES, [report("L"), spec()])
    n = ticket(w)
    assert w.engine.tick() == "awaiting-approval"
    w.tracker.add_label(n, "approved")
    assert w.engine.tick() == "needs-human"
    assert "docs/specs/1.md" in w.builder.calls[0].prompt and len(w.planner.calls) == 2
    assert "needs-approval" not in labels(w)


def test_the_label_wins_over_a_comment_and_the_slash_command_still_works_elsewhere(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)], FILES, [report("L"), spec()])
    n = ticket(w)
    w.engine.tick()
    w.tracker.human_says(n, "also mention floats")
    w.tracker.add_label(n, "approved")
    assert w.engine.tick() == "needs-human" and len(w.planner.calls) == 2
