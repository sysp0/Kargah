"""Five-field cron in UTC: `*`, `n`, `a-b`, `a,b`, `*/n`, `a-b/n`. Day-of-week 0..7 (0 and 7 are Sunday) (pure)."""
from __future__ import annotations

from datetime import datetime, timedelta

_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))      # minute, hour, day of month, month, day of week


def _field(text: str, lo: int, hi: int) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        base, slash, step_text = part.partition("/")
        step = int(step_text) if slash else 1
        if step < 1:
            raise ValueError(f"step must be at least 1 in '{part}'")
        if base == "*":
            first, last = lo, hi
        elif "-" in base:
            first, last = (int(x) for x in base.split("-"))
        elif slash:
            raise ValueError(f"'{part}': a step needs * or a range")
        else:
            first = last = int(base)
        if not lo <= first <= last <= hi:
            raise ValueError(f"'{part}' is outside {lo}-{hi}")
        values.update(range(first, last + 1, step))
    return frozenset(values)


def _parse(expr: str) -> tuple[tuple[frozenset[int], ...], bool]:
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"a cron expression has 5 fields, not {len(fields)}")
    try:
        sets = [_field(f, lo, hi) for f, (lo, hi) in zip(fields, _LIMITS, strict=True)]
    except ValueError as exc:
        raise ValueError(f"bad cron expression '{expr}': {exc}") from exc
    sets[4] = frozenset(d % 7 for d in sets[4])                       # 7 is Sunday too
    return tuple(sets), not fields[2].startswith("*") and not fields[4].startswith("*")


def validate(expr: str) -> str | None:
    try:
        _parse(expr)
    except ValueError as exc:
        return str(exc)
    return None


def _hit(parsed: tuple[tuple[frozenset[int], ...], bool], dt: datetime) -> bool:
    (minute, hour, dom, month, dow), either_day = parsed
    day = ((dt.day in dom or dt.isoweekday() % 7 in dow) if either_day         # both restricted: OR, as in cron
           else dt.day in dom and dt.isoweekday() % 7 in dow)
    return dt.minute in minute and dt.hour in hour and dt.month in month and day


def matches(expr: str, dt: datetime) -> bool:
    return _hit(_parse(expr), dt)


def latest_slot(expr: str, now: datetime, lookback: timedelta = timedelta(days=7)) -> datetime | None:
    """The newest minute at or before `now` (within the lookback) that matches; looks back minute by minute."""
    parsed, start = _parse(expr), now.replace(second=0, microsecond=0)
    for back in range(int(lookback.total_seconds() // 60) + 1):
        if _hit(parsed, slot := start - timedelta(minutes=back)):
            return slot
    return None
