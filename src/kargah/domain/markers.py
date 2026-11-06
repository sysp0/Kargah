"""How the bot signs its comments, and how a comment is recognised (and read) as the bot's."""
from __future__ import annotations

import re
from dataclasses import dataclass

MARKER_PREFIX = "<!-- kargah:"
_MARKER = re.compile(r"<!-- kargah:(?P<kind>[\w-]+)(?P<attrs>(?: [\w-]+=\S+)*) -->")


@dataclass(frozen=True)
class Marker:
    kind: str
    attrs: dict[str, str]


def bot_comment(kind: str, run: str, text: str, **attrs: object) -> str:
    """A visible header for people and a hidden marker for the engine. Attribute values contain no spaces."""
    extra = "".join(f" {k}={v}" for k, v in attrs.items())
    return f"**kargah-bot** · {kind} · run {run}\n\n{text}\n\n{MARKER_PREFIX}{kind} run={run}{extra} -->"


def carries_marker(body: str) -> bool:
    return MARKER_PREFIX in body


def parse_marker(body: str) -> Marker | None:
    found = list(_MARKER.finditer(body))
    if not found:
        return None
    last = found[-1]
    attrs = dict(pair.split("=", 1) for pair in last["attrs"].split())
    return Marker(last["kind"], attrs)
