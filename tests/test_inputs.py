from datetime import UTC, datetime, timedelta

from kargah.domain.inputs import human_input, is_bot_comment
from kargah.domain.markers import bot_comment
from kargah.domain.ticket import Author, Comment

BOT, OWNER = Author(1, "kargah-bot"), Author(2, "owner")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def say(i: int, author: Author, body: str) -> Comment:
    return Comment(i, author, body, T0 + timedelta(seconds=i))


def test_human_answer_after_the_bots_question_is_input():
    comments = [say(1, OWNER, "do X"), say(2, BOT, "which column?"), say(3, OWNER, "created_at")]
    assert [c.id for c in human_input(comments, BOT.id)] == [3]


def test_bot_speaking_last_means_no_input():
    comments = [say(1, OWNER, "do X"), say(2, BOT, "which column?")]
    assert human_input(comments, BOT.id) == ()


def test_the_bots_own_comments_are_never_input_even_in_a_row():
    comments = [say(i, BOT, f"progress {i}") for i in range(1, 6)]
    assert human_input(comments, BOT.id) == ()


def test_a_marked_comment_is_not_input_even_from_another_author():
    marked = say(2, OWNER, bot_comment("question", "7", "which column?"))
    assert is_bot_comment(marked, BOT.id)
    assert human_input([marked], BOT.id) == ()


def test_several_human_comments_after_the_bot_are_all_input_in_order():
    comments = [say(1, BOT, "q"), say(3, OWNER, "b"), say(2, OWNER, "a")]
    assert [c.body for c in human_input(comments, BOT.id)] == ["a", "b"]


def test_without_any_bot_comment_all_human_comments_are_input():
    assert len(human_input([say(1, OWNER, "a")], BOT.id)) == 1
