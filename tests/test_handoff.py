from datetime import UTC, datetime, timedelta

from kargah.domain.decision import Action
from kargah.domain.handoff import decide_handoff, format_items, parse_items, revise_items
from kargah.domain.markers import bot_comment
from kargah.domain.ticket import Author, Comment, Ticket
from kargah.ports.githost import Discussion, MrView

BOT, OWNER = Author(1, "bot"), Author(2, "owner")
T0 = datetime(2026, 1, 1, tzinfo=UTC)
TICKET = Ticket(1, "t", "", frozenset({"needs-human"}))
CLOSED = Ticket(1, "t", "", frozenset({"needs-human"}), open=False)


def mr(state="opened"):
    return MrView(3, "u", state, T0, T0 if state == "merged" else None)


def comment(i, author, body):
    return Comment(i, author, body, T0 + timedelta(minutes=i))


def ready(i=1):
    return comment(i, BOT, bot_comment("ready", "r1", "done", sha="s"))


def thread(id="d1", body="rename this", path="a.py", line=3):
    return Discussion(id, OWNER, body, path, line, T0)


def action(ticket=TICKET, comments=(), view=None, discussions=(), state="opened"):
    return decide_handoff(ticket, comments, view if view is not None else mr(state), discussions, BOT.id).action


def test_rule_1_a_missing_mr_blocks():
    assert decide_handoff(TICKET, [], None, [], BOT.id).action is Action.BLOCK


def test_rule_2_merged_completes_even_if_the_issue_is_closed_or_threads_are_open():
    assert action(state="merged") is Action.COMPLETE
    assert action(CLOSED, state="merged", discussions=[thread()]) is Action.COMPLETE


def test_rule_3_a_closed_mr_blocks():
    assert action(state="closed") is Action.BLOCK


def test_rule_4_a_closed_issue_with_an_open_mr_cancels():
    assert action(CLOSED, discussions=[thread()]) is Action.CANCEL


def test_rule_5_a_diff_thread_or_a_revise_comment_asks_for_changes():
    assert action(discussions=[thread()]) is Action.REVISE
    assert action(comments=[ready(1), comment(2, OWNER, "/revise handle empty input")]) is Action.REVISE


def test_rule_6_nothing_to_do_waits():
    assert action(comments=[ready()]) is Action.SKIP


def test_a_revise_comment_before_the_last_handoff_is_ignored():
    comments = [comment(1, OWNER, "/revise old request"), ready(2)]
    assert action(comments=comments) is Action.SKIP


def test_a_plain_comment_is_not_an_order():
    comments = [ready(1), comment(2, OWNER, "thanks, looks good so far"), comment(3, OWNER, "/reviser x")]
    assert action(comments=comments) is Action.SKIP


def test_the_bots_own_text_never_counts_even_with_the_command():
    comments = [ready(1), comment(2, BOT, "/revise do it again")]
    assert revise_items(comments, [], BOT.id) == ()


def test_items_carry_where_and_text_and_survive_the_round_trip():
    items = revise_items([ready(1), comment(2, OWNER, "/revise\nuse a helper")], [thread(body="line one\nline two")], BOT.id)
    assert [(i.source, i.where, i.text) for i in items] == [("mr", "a.py:3", "line one\nline two"),
                                                            ("issue", "", "use a helper")]
    assert parse_items(format_items(items)) == ("a.py:3: line one line two", "use a helper")


def test_empty_revise_is_not_an_item():
    assert revise_items([ready(1), comment(2, OWNER, "/revise")], [], BOT.id) == ()
