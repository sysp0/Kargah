"""domain/cron.py: five fields, UTC, standard OR rule between day-of-month and day-of-week."""
from datetime import UTC, datetime, timedelta

import pytest

from kargah.domain.cron import latest_slot, matches, validate

# 2026-01-05 is a Monday; 2026-01-04 a Sunday; 2026-01-15 a Thursday.
MON_9 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
SUN_9 = datetime(2026, 1, 4, 9, 0, tzinfo=UTC)
THU_15 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize("expr, when, expected", [
    ("0 9 * * 1", MON_9, True),
    ("0 9 * * 1", MON_9 + timedelta(minutes=1), False),
    ("0 9 * * 1", SUN_9, False),
    ("* * * * *", MON_9 + timedelta(minutes=37), True),
    ("*/15 * * * *", MON_9 + timedelta(minutes=45), True),
    ("*/15 * * * *", MON_9 + timedelta(minutes=46), False),
    ("0 9 * * 0", SUN_9, True),                   # Sunday as 0
    ("0 9 * * 7", SUN_9, True),                   # Sunday as 7
    ("0 9 * * 1-5", MON_9, True),
    ("0 9 * * 1-5", SUN_9, False),
    ("0,30 9 * * *", MON_9 + timedelta(minutes=30), True),
    ("0,30 9 * * *", MON_9 + timedelta(minutes=15), False),
    ("10-50/20 9 * * *", MON_9 + timedelta(minutes=30), True),     # 10, 30, 50
    ("10-50/20 9 * * *", MON_9 + timedelta(minutes=20), False),
    ("0 */6 * * *", MON_9.replace(hour=18), True),
    ("0 */6 * * *", MON_9.replace(hour=9), False),
    ("0 9 15 * *", THU_15, True),                 # only day-of-month restricted
    ("0 9 15 * *", MON_9, False),
    ("0 9 15 * 1", THU_15, True),                 # both restricted: OR (the 15th ...)
    ("0 9 15 * 1", MON_9, True),                  # ... or a Monday
    ("0 9 15 * 1", SUN_9, False),
    ("0 9 * 1 *", MON_9, True),                   # month January
    ("0 9 * 2 *", MON_9, False),
])
def test_matches(expr, when, expected):
    assert matches(expr, when) is expected


@pytest.mark.parametrize("bad", ["", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *",
                                 "* * * * 8", "*/0 * * * *", "5-1 * * * *", "a * * * *", "1/5 * * * *", "-1 * * * *"])
def test_invalid_expressions_are_reported(bad):
    assert validate(bad)
    with pytest.raises(ValueError):
        matches(bad, MON_9)


def test_a_valid_expression_has_no_problem():
    assert validate("*/15 0-6 1,15 * 1-5") is None


def test_latest_slot_is_now_when_now_matches_and_otherwise_the_previous_one():
    assert latest_slot("0 9 * * *", MON_9) == MON_9
    assert latest_slot("0 9 * * *", MON_9 + timedelta(hours=5, seconds=30)) == MON_9
    assert latest_slot("0 9 * * 1", MON_9 + timedelta(days=3)) == MON_9


def test_latest_slot_catches_up_only_the_newest_missed_slot():
    assert latest_slot("0 9 * * *", MON_9 + timedelta(days=5, hours=2)) == MON_9 + timedelta(days=5)


def test_latest_slot_gives_up_after_the_lookback():
    assert latest_slot("0 9 5 1 *", MON_9 + timedelta(days=8)) is None          # 8 days after the only slot
    assert latest_slot("0 9 * * 1", MON_9 + timedelta(days=6, hours=23)) == MON_9
    assert latest_slot("0 0 1 6 *", MON_9) is None
