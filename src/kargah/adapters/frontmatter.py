"""TOML frontmatter between two `+++` lines, shared by agent and scorer files."""
from __future__ import annotations

import re
import tomllib

from kargah.errors import KargahError

_FRONT = re.compile(r"\A\+\+\+\r?\n(.*?)^\+\+\+[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S | re.M)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """(frontmatter table, body). No `+++` block means no frontmatter. Raises KargahError on bad TOML."""
    found = _FRONT.match(text)
    if not found:
        return {}, text.strip()
    try:
        return tomllib.loads(found[1]), found[2].strip()
    except tomllib.TOMLDecodeError as exc:
        raise KargahError(f"frontmatter is not valid TOML: {exc}") from exc
