"""Live bug (sandbox #34): the reviewer must see the owner's comments, they are decisions that change the ticket."""
from engine_fixtures import make_world, multiply_feature, says
from test_engine import PASS


def test_the_reviewer_is_told_what_the_owner_decided_in_comments(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    n = w.tracker.open_ticket("add multiply", "add multiply(a, b). Touch no other file.", ("ready",))
    w.tracker.human_says(n, "A test file is allowed here, the proof is not waived.")
    assert w.engine.tick() == "needs-human"
    prompt = w.reviewer.calls[0].prompt
    assert "A test file is allowed here" in prompt and "decisions" in prompt


def test_the_reviewer_prompt_has_no_comment_block_when_the_owner_said_nothing(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    w.engine.tick()
    assert "The owner's comments" not in w.reviewer.calls[0].prompt


def test_a_rework_that_changes_nothing_after_the_owner_overruled_the_review_goes_back_to_review(tmp_path):
    """Live (sandbox #34): the owner overruled a must-fix; the builder rightly changed nothing."""
    w = make_world(tmp_path, [multiply_feature(), says("QUESTION: drop the reviewer's item?"),
                              says("The owner allowed it, nothing to change.")],
                   [says("VERDICT: MUST_FIX\nMUST-FIX: remove the test file"), says(PASS)])
    n = w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "question"
    w.tracker.human_says(n, "Yes, drop that item.")
    assert w.engine.tick() == "needs-human"
    assert len(w.reviewer.calls) == 2 and "Kargah-State: complete" in w.remote_log("kargah/1")
