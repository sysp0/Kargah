from kargah.domain.stages import Progress, Review, Stage, next_stage


def progress(head="h2", complete=True, reviews=(), feedback_sha=None, since=None, open_=False):
    return Progress(True, head, complete, tuple(reviews), feedback_sha, open_, since)


def test_a_feedback_marker_on_the_current_head_means_rework_before_anything_else():
    old_pass = [Review("h2", 0)]
    assert next_stage(progress(reviews=old_pass, feedback_sha="h2", open_=True), 2) is Stage.REWORK


def test_after_the_rework_commit_the_normal_path_continues_with_review_then_pass():
    assert next_stage(progress(head="h3", reviews=[Review("h2", 0)], feedback_sha="h2", open_=True), 2) is Stage.REVIEW
    reviews = [Review("h2", 0), Review("h3", 0)]
    assert next_stage(progress(head="h3", reviews=reviews, feedback_sha="h2", since=(Review("h3", 0),)), 2) is Stage.PASS


def test_rework_rounds_are_counted_only_after_the_owners_feedback():
    failed = [Review("a", 1), Review("b", 1), Review("c", 1)]
    assert next_stage(progress(head="c", reviews=failed), 2) is Stage.BLOCKED
    after_feedback = progress(head="c", reviews=failed, feedback_sha="x", since=(Review("c", 1),))
    assert next_stage(after_feedback, 2) is Stage.REWORK


def test_no_feedback_keeps_the_old_behaviour():
    assert next_stage(Progress(True, "h", True, ()), 2) is Stage.REVIEW
    assert next_stage(Progress(True, "h", False, ()), 2) is Stage.BUILD
