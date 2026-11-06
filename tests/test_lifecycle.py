"""The life of a ticket after the handoff: merge, close, change requests (plan phase 3)."""
import json

from engine_fixtures import MULTIPLY_CODE, make_world, multiply_feature, says, writes

from kargah.domain.markers import parse_marker

PASS = "VERDICT: PASS"
MUST_FIX = "VERDICT: MUST_FIX\nMUST-FIX: multiply ignores floats"
BRANCH = "kargah/1"


def labels(w, n=1):
    return set(w.tracker.get_ticket(n).labels)


def handed_over(tmp_path, builder=(), reviewer=()):
    w = make_world(tmp_path, [multiply_feature(), *builder], [says(PASS), *reviewer])
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "needs-human"
    return w


def records(w, kind):
    return [r for r in map(json.loads, w.log()) if r.get("kind", "run") == kind]


def markers(w, kind):
    return [c for c in w.tracker.comments(1) if (m := parse_marker(c.body)) and m.kind == kind]


def edit(tag):
    return writes({"src/calc/ops.py": MULTIPLY_CODE + f"\n# {tag}\n"})


# ---- complete / cancel / block ------------------------------------------------------------------------------------
def test_a_merged_mr_completes_the_ticket_without_any_agent(tmp_path):
    w = handed_over(tmp_path)
    w.tracker.human_says(1, "looks good")
    w.host.say(BRANCH, "nice")
    w.host.authors[BRANCH].append("owner@x")
    w.clock.advance(hours=3)
    w.host.merge(BRANCH)
    calls = (len(w.builder.calls), len(w.reviewer.calls))
    assert w.engine.tick() == "idle"
    assert (len(w.builder.calls), len(w.reviewer.calls)) == calls
    assert labels(w) == {"done"} and not w.tracker.get_ticket(1).open
    assert len(markers(w, "done")) == 1 and "Merged: https://example/mr/kargah/1" in markers(w, "done")[0].body
    [done] = records(w, "completion")
    assert (done["outcome"], done["ticket"], done["mr_url"]) == ("merged", 1, "https://example/mr/kargah/1")
    assert done["human_interactions"] == 3 and done["human_pushed"] is True
    assert done["kickoff_at"] and done["handoff_at"] and done["first_human_review_at"] and done["merged_at"]
    assert w.engine.tick() == "idle" and len(records(w, "completion")) == 1      # nothing happens twice


def test_completion_of_a_hands_off_ticket_counts_no_human_work(tmp_path):
    w = handed_over(tmp_path)
    w.host.merge(BRANCH)
    w.engine.tick()
    [done] = records(w, "completion")
    assert (done["human_interactions"], done["human_pushed"], done["first_human_review_at"]) == (0, False, None)


def test_a_closed_issue_with_an_open_mr_is_cancelled_and_the_branch_is_kept(tmp_path):
    w = handed_over(tmp_path)
    w.tracker.close_ticket(1)
    assert w.engine.tick() == "idle"
    assert labels(w) == set() and len(markers(w, "cancelled")) == 1
    assert "Cancelled" in markers(w, "cancelled")[0].body
    assert records(w, "completion")[0]["outcome"] == "cancelled"
    assert w.engine.tick() == "idle" and len(markers(w, "cancelled")) == 1


def test_a_merged_mr_wins_over_a_closed_issue(tmp_path):
    w = handed_over(tmp_path)
    w.tracker.close_ticket(1)
    w.host.merge(BRANCH)
    w.engine.tick()
    assert labels(w) == {"done"}


def test_a_mr_closed_without_merging_blocks_the_ticket(tmp_path):
    w = handed_over(tmp_path)
    w.host.close(BRANCH)
    w.engine.tick()
    assert labels(w) == {"blocked"} and "closed without merging" in markers(w, "blocked")[0].body


def test_an_issue_closed_during_a_run_stops_it_and_cancels(tmp_path):
    holder = {}

    def closing(request):
        holder["w"].tracker.close_ticket(1)
        return multiply_feature()(request)

    w = make_world(tmp_path, [closing], [])
    holder["w"] = w
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    assert w.engine.tick() == "cancelled"
    assert labels(w) == set() and w.reviewer.calls == []
    assert "feat: #1 add multiply" in w.remote_log(BRANCH)             # the finished step is kept on the branch
    assert records(w, "completion")[0]["outcome"] == "cancelled"


def test_a_merge_during_rework_stops_the_run_and_completes(tmp_path):
    holder = {}

    def merging(request):
        holder["w"].host.merge(BRANCH)
        return edit("late")(request)

    w = handed_over(tmp_path)
    holder["w"] = w
    w.builder.steps.append(merging)
    w.reviewer.steps.append(says(PASS))
    w.host.comment_on_diff(BRANCH, "please add a comment")
    assert w.engine.tick() == "done"
    assert labels(w) == {"done"} and len(w.reviewer.calls) == 1


# ---- change requests ----------------------------------------------------------------------------------------------
def test_a_diff_comment_is_reworked_reviewed_again_and_the_thread_is_resolved(tmp_path):
    w = handed_over(tmp_path, [edit("renamed")], [says(PASS)])
    thread = w.host.comment_on_diff(BRANCH, "rename the helper")
    assert w.engine.tick() == "needs-human"
    assert "The owner asked for changes" in w.builder.calls[1].prompt
    assert "src/calc/ops.py:2: rename the helper" in w.builder.calls[1].prompt
    assert len(w.reviewer.calls) == 2                                  # the review runs again
    assert [t for t, _ in w.host.resolved] == [thread] and "Addressed in" in w.host.resolved[0][1]
    assert labels(w) == {"needs-human"} and len(markers(w, "feedback")) == 1
    assert w.engine.tick() == "idle"                                   # nothing open any more


def test_a_revise_comment_on_the_issue_works_like_a_diff_comment(tmp_path):
    w = handed_over(tmp_path, [edit("floats")], [says(PASS)])
    w.tracker.human_says(1, "/revise support floats too")
    assert w.engine.tick() == "needs-human"
    assert "support floats too" in w.builder.calls[1].prompt and w.host.resolved == []
    assert w.engine.tick() == "idle"                                   # the old /revise is before the new handoff


def test_plain_comments_and_old_revise_comments_start_nothing(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    w.tracker.human_says(1, "/revise this came before the handoff")
    assert w.engine.tick() == "needs-human"
    w.tracker.human_says(1, "thanks, I will look tomorrow")
    assert w.engine.tick() == "idle" and len(w.builder.calls) == 1


def test_owner_requests_do_not_use_up_the_rework_rounds(tmp_path):
    w = handed_over(tmp_path, [edit("a"), edit("b"), edit("c"), edit("d")],
                    [says(MUST_FIX), says(PASS), says(MUST_FIX), says(PASS)])
    w.host.comment_on_diff(BRANCH, "first request")
    assert w.engine.tick() == "needs-human"            # review failed once after the request, then passed
    w.tracker.human_says(1, "/revise second request")
    assert w.engine.tick() == "needs-human"


def test_a_run_that_dies_after_the_feedback_comment_is_continued_not_re_delivered(tmp_path):
    def dies(request):
        raise RuntimeError("power cut")

    w = handed_over(tmp_path, [dies, edit("after crash")], [says(PASS)])
    w.host.comment_on_diff(BRANCH, "handle zero")
    try:
        w.engine.tick()
    except RuntimeError:
        pass
    assert labels(w) == {"in-progress"} and len(markers(w, "feedback")) == 1
    assert w.engine.tick() == "needs-human"
    assert "handle zero" in w.builder.calls[2].prompt                  # reworked from the recorded request
    assert len(markers(w, "feedback")) == 1 and len(w.reviewer.calls) == 2
    assert len(markers(w, "ready")) == 2


def test_a_run_that_dies_after_the_ready_comment_does_not_post_it_twice(tmp_path):
    w = make_world(tmp_path, [multiply_feature()], [says(PASS)])
    original, state = w.tracker.add_label, {"failed": False}

    def flaky(number, label):
        if label == "needs-human" and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("network down")
        original(number, label)

    w.tracker.add_label = flaky
    w.tracker.open_ticket("add multiply", "add multiply(a, b)", ("ready",))
    try:
        w.engine.tick()
    except RuntimeError:
        pass
    assert w.engine.tick() == "needs-human"
    assert len(markers(w, "ready")) == 1


def test_blocking_twice_after_a_crash_between_comment_and_label_posts_one_comment(tmp_path):
    w = handed_over(tmp_path)
    w.host.close(BRANCH)
    original, state = w.tracker.add_label, {"failed": False}

    def flaky(number, label):
        if label == "blocked" and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("network down")
        original(number, label)

    w.tracker.add_label = flaky
    try:
        w.engine.tick()
    except RuntimeError:
        pass
    w.engine.tick()
    assert labels(w) == {"blocked"} and len(markers(w, "blocked")) == 1


def test_an_interrupt_label_keeps_change_requests_waiting(tmp_path):
    w = handed_over(tmp_path)
    w.host.comment_on_diff(BRANCH, "change this")
    w.tracker.add_label(1, "interrupt")
    assert w.engine.tick() == "idle" and len(w.builder.calls) == 1


def test_stops_are_counted_since_the_last_handoff_only(tmp_path):
    w = handed_over(tmp_path, [edit("a"), edit("b"), edit("c"), edit("d"), edit("e"), edit("f")],
                    [says(PASS)] * 6)
    for i in range(6):                          # more rounds than max_starts
        w.tracker.human_says(1, f"/revise change number {i}")
        assert w.engine.tick() == "needs-human"
    assert "blocked" not in labels(w)
