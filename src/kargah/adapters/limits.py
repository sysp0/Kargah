"""Reading a usage-limit message of Codex or Claude: is it a limit, and when does it end (never guessed)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIMIT_RE = re.compile(r"usage limit|rate limit|session limit|quota|too many requests|try again (in|at)", re.I)
_IN = re.compile(r"try again in ([^\n\"]{1,80})", re.I)
_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_DURATION = re.compile(r"(\d+)\s*(day|d|hour|hr|h|minute|min|m|second|sec|s)", re.I)
_CLOCK = re.compile(r"(?:resets|try again at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)\s]+)\))?", re.I)


def is_limit(text: str) -> bool:
    return bool(LIMIT_RE.search(text))


def resets_at(text: str, now: datetime) -> datetime | None:
    """`try again in 2 hours 5 minutes` or `resets 4am (Europe/Berlin)` / `try again at 6:44 PM`; else None."""
    if m := _IN.findall(text):
        seconds = sum(int(n) * _UNITS[u[0].lower()] for n, u in _DURATION.findall(m[-1]))
        return now + timedelta(seconds=seconds) if seconds else None
    if m := _CLOCK.findall(text):
        hour, minute, half, zone = m[-1]
        h = int(hour) % 12 + (12 if half.lower() == "pm" else 0) if half else int(hour)
        try:
            tz = ZoneInfo(zone) if zone else now.tzinfo
        except (ZoneInfoNotFoundError, ValueError):
            tz = now.tzinfo
        local = now.astimezone(tz)
        at = local.replace(hour=h % 24, minute=int(minute or 0), second=0, microsecond=0)
        return at + timedelta(days=1) if at <= local else at
    return None
