"""Where a ticket stands, read from git and from the bot's own markers (no state in the engine).

`next_stage` is a table: the first rule that matches wins."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kargah.domain.triage import TriageReport, size_rank


class Stage(StrEnum):
    TRIAGE = "triage"
    SPEC = "spec"
    AWAIT_APPROVAL = "await-approval"
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
class SpecView:
    sha: str
    approved: bool             # the owner's last comment after the spec starts with /approve
    changes_requested: bool    # the owner commented after the spec and the last comment is not /approve


@dataclass(frozen=True)
class Policy:
    """From `[stages]` in the project config, plus one fact about the ticket."""
    triage: str = "never"            # auto | always | never
    spec: str = "never"
    spec_min_size: str = "L"
    body_has_acceptance: bool = False


@dataclass(frozen=True)
class Progress:
    has_work: bool          # the branch has commits beyond the base
    head_sha: str
    head_complete: bool     # HEAD carries `Kargah-State: complete`
    reviews: tuple[Review, ...]
    feedback_sha: str | None = None          # HEAD when the owner's last change request was recorded
    feedback_open: bool = False              # that request has no review after it yet
    reviews_since_feedback: tuple[Review, ...] | None = None      # None: no feedback yet, every review counts
    triage: TriageReport | None = None
    spec: SpecView | None = None
    has_build: bool | None = None            # None: same as has_work (a build or rework commit exists otherwise)


def spec_needed(p: Progress, policy: Policy) -> bool:
    if policy.spec == "always":
        return True
    if policy.spec != "auto" or p.triage is None:
        return False
    return size_rank(p.triage.size) >= size_rank(policy.spec_min_size) or p.triage.ambiguous


def next_stage(p: Progress, max_rework: int, policy: Policy | None = None) -> Stage:
    policy = policy or Policy()
    if p.triage is None and (policy.triage == "always" or (policy.triage == "auto" and not policy.body_has_acceptance)):
        return Stage.TRIAGE
    if p.spec is None and spec_needed(p, policy):
        return Stage.SPEC
    if p.spec is not None and not p.spec.approved:
        return Stage.SPEC if p.spec.changes_requested else Stage.AWAIT_APPROVAL
    if p.feedback_sha == p.head_sha:
        return Stage.REWORK                  # the owner asked for changes on this very commit
    built = p.has_work if p.has_build is None else p.has_build
    if not built or not p.head_complete:
        return Stage.BUILD
    here = [r for r in p.reviews if r.sha == p.head_sha]
    if not here:
        return Stage.REVIEW
    if here[-1].must_fix == 0:
        return Stage.PASS
    counted = p.reviews if p.reviews_since_feedback is None else p.reviews_since_feedback
    failed_rounds = sum(1 for r in counted if r.must_fix > 0)
    return Stage.BLOCKED if failed_rounds > max_rework else Stage.REWORK
