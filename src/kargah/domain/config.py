"""Project settings: the small contract a project gives the factory (read from .kargah/config.toml)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from kargah.domain.pricing import ModelPrice


@dataclass(frozen=True)
class ProjectConfig:
    base_branch: str = "main"
    check_command: str = "scripts/check.sh"
    proof_command: str = "python3 -m pytest -q"
    proof_test_paths: tuple[str, ...] = ("tests/",)
    proof_fail_codes: tuple[int, ...] = (1, 2)   # pytest: 1 = a test failed, 2 = collection error (missing code)
    max_fix_rounds: int = 1       # extra build rounds inside one run after a failed check or proof
    max_rework: int = 2           # review-driven rework rounds before the ticket is blocked
    max_starts: int = 5           # stopped runs recovered before the ticket is blocked
    build_timeout_seconds: int = 1800
    review_timeout_seconds: int = 600
    review_model: str = "claude-sonnet-5-5"
    build_model: str = ""         # empty: the harness default
    prices: Mapping[str, ModelPrice] = field(default_factory=dict)    # [pricing."<model>"], USD per million tokens
    runs_keep_days: int = 30      # step folders (prompt, reply, diff) older than this are deleted; records stay
