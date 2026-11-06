"""Where a ticket stands, read from git and from the bot's own markers (no state in the engine)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Stage(StrEnum):
    BUILD = "build"
    REVIEW = "review"
    REWORK = "rework"
    PASS = "pass"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Review:
    sha: str
    must_fix: int


@dataclass(frozen=True)
class Progress:
    has_work: bool          # the branch has commits beyond the base
    head_sha: str
    head_complete: bool     # HEAD carries `Kargah-State: complete`
    reviews: tuple[Review, ...]


def next_stage(p: Progress, max_rework: int) -> Stage:
    if not p.has_work or not p.head_complete:
        return Stage.BUILD
    here = [r for r in p.reviews if r.sha == p.head_sha]
    if not here:
        return Stage.REVIEW
    if here[-1].must_fix == 0:
        return Stage.PASS
    failed_rounds = sum(1 for r in p.reviews if r.must_fix > 0)
    return Stage.BLOCKED if failed_rounds > max_rework else Stage.REWORK
