from datetime import UTC, datetime, timedelta

from kargah.domain.decision import Action, decide
from kargah.domain.markers import bot_comment, parse_marker
from kargah.domain.review import parse_question, parse_verdict
from kargah.domain.stages import Progress, Review, Stage, next_stage
from kargah.domain.ticket import Author, Comment, Ticket

BOT, OWNER = Author(1, "bot"), Author(2, "owner")
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def ticket(*labels: str) -> Ticket:
    return Ticket(1, "t", "", frozenset(labels))


def say(i: int, author: Author, body: str) -> Comment:
    return Comment(i, author, body, NOW - timedelta(hours=10 - i))


def test_marker_round_trip_with_attributes():
    m = parse_marker(bot_comment("limit", "7", "wait", resume_at="2026-01-01T13:00:00+00:00"))
    assert m is not None and m.kind == "limit" and m.attrs["resume_at"] == "2026-01-01T13:00:00+00:00"


def test_ready_starts_and_interrupt_blocks_everything():
    assert decide(ticket("ready"), [], BOT.id, NOW, 5).action is Action.START
    assert decide(ticket("ready", "interrupt"), [], BOT.id, NOW, 5).action is Action.SKIP


def test_needs_info_resumes_only_after_a_human_answer():
    asked = [say(1, BOT, bot_comment("question", "1", "which?"))]
    assert decide(ticket("needs-info"), asked, BOT.id, NOW, 5).action is Action.SKIP
    answered = [*asked, say(2, OWNER, "this one")]
    assert decide(ticket("needs-info"), answered, BOT.id, NOW, 5).action is Action.RESUME


def test_limit_waits_for_the_reset_time_then_resumes():
    later = (NOW + timedelta(hours=1)).isoformat()
    waiting = [say(1, BOT, bot_comment("limit", "1", "x", resume_at=later))]
    assert decide(ticket("in-progress"), waiting, BOT.id, NOW, 5).action is Action.SKIP
    assert decide(ticket("in-progress"), waiting, BOT.id, NOW + timedelta(hours=2), 5).action is Action.RESUME


def test_a_crashed_run_is_recovered_a_limited_number_of_times():
    started = [say(i, BOT, bot_comment("started", str(i), "go")) for i in range(1, 6)]
    assert decide(ticket("in-progress"), started[:2], BOT.id, NOW, 5).action is Action.RESUME
    assert decide(ticket("in-progress"), started, BOT.id, NOW, 5).action is Action.BLOCK


def test_stages_follow_git_and_reviews():
    head = "abc"
    base = dict(has_work=True, head_sha=head, head_complete=True)
    assert next_stage(Progress(False, "", False, ()), 2) is Stage.BUILD
    assert next_stage(Progress(True, head, False, ()), 2) is Stage.BUILD
    assert next_stage(Progress(reviews=(), **base), 2) is Stage.REVIEW
    assert next_stage(Progress(reviews=(Review(head, 0),), **base), 2) is Stage.PASS
    assert next_stage(Progress(reviews=(Review("old", 1),), **base), 2) is Stage.REVIEW
    assert next_stage(Progress(reviews=(Review(head, 1),), **base), 2) is Stage.REWORK
    assert next_stage(Progress(reviews=(Review("a", 1), Review("b", 1), Review(head, 1)), **base), 2) is Stage.BLOCKED


def test_verdict_parsing():
    v = parse_verdict("VERDICT: MUST_FIX\nMUST-FIX: no test\nSHOULD: rename\nNIT: typo")
    assert v is not None and not v.passed and v.must_fix == ("no test",) and v.should == ("rename",)
    assert parse_verdict("VERDICT: PASS\nNIT: x").passed
    assert not parse_verdict("VERDICT: PASS\nMUST-FIX: contradiction").passed
    assert parse_verdict("looks good to me") is None


def test_builder_question_is_the_last_question_line():
    assert parse_question("done\nQUESTION: which column?") == "which column?"
    assert parse_question("all done") is None


def test_a_nested_keyword_is_reclassified_and_empty_items_are_dropped():
    v = parse_verdict("VERDICT: PASS\nMUST-FIX: SHOULD: add a case\nNIT: none")
    assert v is not None and v.passed and v.must_fix == () and v.should == ("add a case",) and v.nit == ()


def test_must_fix_verdict_without_a_named_problem_is_a_format_violation():
    assert parse_verdict("VERDICT: MUST_FIX\nSHOULD: something") is None
