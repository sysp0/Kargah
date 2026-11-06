"""The reviewer's verdict format and its parser (pure)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_VERDICT = re.compile(r"^VERDICT:\s*(PASS|MUST_FIX)\s*$", re.M)
_ITEM = re.compile(r"^(MUST-FIX|SHOULD|NIT):\s*(.+)$", re.M)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    must_fix: tuple[str, ...]
    should: tuple[str, ...]
    nit: tuple[str, ...]


def parse_verdict(text: str) -> Verdict | None:
    """None when the reply does not follow the format (the caller treats that as a failed review)."""
    found = _VERDICT.findall(text)
    if not found:
        return None
    items: dict[str, list[str]] = {"MUST-FIX": [], "SHOULD": [], "NIT": []}
    for kind, body in _ITEM.findall(text):
        kind, body = _reclassify(kind, body.strip())
        if body.lower().rstrip(".") not in _EMPTY:
            items[kind].append(body)
    if found[-1] == "MUST_FIX" and not items["MUST-FIX"]:
        return None      # says "must fix" but names nothing: a format violation, a human must look
    passed = found[-1] == "PASS" and not items["MUST-FIX"]
    return Verdict(passed, tuple(items["MUST-FIX"]), tuple(items["SHOULD"]), tuple(items["NIT"]))


_EMPTY = {"", "none", "n/a", "nothing", "no issues", "-"}
_NESTED = re.compile(r"^(SHOULD|NIT|MUST-FIX):\s*(.+)$", re.S)


def _reclassify(kind: str, body: str) -> tuple[str, str]:
    """A model sometimes writes `MUST-FIX: SHOULD: text`; the inner keyword wins."""
    nested = _NESTED.match(body)
    return (nested[1], nested[2].strip()) if nested else (kind, body)


def parse_question(text: str) -> str | None:
    """A builder that cannot go on ends its reply with a `QUESTION:` line."""
    found = re.findall(r"^QUESTION:\s*(.+)$", text, re.M)
    return found[-1].strip() if found else None
