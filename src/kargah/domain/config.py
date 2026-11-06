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
    max_fix_rounds: int = 2       # extra build rounds inside one run after a failed check or proof
    max_rework: int = 3           # review-driven rework rounds before the ticket is blocked
    max_starts: int = 5           # stopped runs recovered before the ticket is blocked
    triage_policy: str = "auto"   # [stages] triage: auto (when the body has no acceptance section) | always | never
    spec_policy: str = "auto"     # [stages] spec: auto (size >= spec_min_size or an ambiguity) | always | never
    spec_min_size: str = "L"
    check_timeout_seconds: int = 1800     # one run of the check or of the proof command
    prices: Mapping[str, ModelPrice] = field(default_factory=dict)    # [pricing."<model>"], USD per million tokens
    proof_exempt_paths: tuple[str, ...] = (".kargah/", "docs/")     # a change only under these needs no new test
    self_improvement: bool = False           # [self_improvement] enabled: open issues about failing agents
    improvement_failed_threshold: int = 5    # failed scores of one role that make an issue
    improvement_max_age_days: int = 7        # or: the oldest unclaimed failure is this old
    runs_keep_days: int = 30      # step folders (prompt, reply, diff) older than this are deleted; records stay
