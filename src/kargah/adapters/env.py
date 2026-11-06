"""The environment an agent or project command gets: no tokens, no secrets of the factory."""
from __future__ import annotations

import os
from collections.abc import Iterable

_SECRET_WORDS = ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL")


def clean_env(allow: Iterable[str] = ()) -> dict[str, str]:
    """Copy of os.environ without KARGAH_* and anything that looks like a secret, except names in `allow`."""
    allowed = set(allow)
    return {k: v for k, v in os.environ.items()
            if k in allowed or not (k.startswith("KARGAH_") or any(w in k.upper() for w in _SECRET_WORDS))}
