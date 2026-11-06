"""The stage table of plan 4.4: every rule with a positive and a negative case."""
import pytest

from kargah.domain.stages import Policy, Progress, Review, SpecView, Stage, next_stage
from kargah.domain.triage import TriageReport

M = TriageReport("M", None, ("works",))
L = TriageReport("L", None, ("works",))
AMBIGUOUS_S = TriageReport("S", "ints or floats?", ("works",))
AUTO = Policy(triage="auto", spec="auto")


def p(**kw):
    base = dict(has_work=True, head_sha="h", head_complete=True, reviews=(), has_build=True)
    return Progress(**{**base, **kw})


def stage(progress, policy=AUTO, max_rework=2):
    return next_stage(progress, max_rework, policy)


CASES = [
    # rule 1: triage
    ("1+ no acceptance in the body, auto", p(has_build=False, head_complete=False), AUTO, Stage.TRIAGE),
    ("1+ always, even with acceptance", p(has_build=False), Policy("always", "never", body_has_acceptance=True), Stage.TRIAGE),
    ("1- acceptance in the body, auto", p(has_build=False), Policy("auto", "never", body_has_acceptance=True), Stage.BUILD),
    ("1- never", p(has_build=False), Policy("never", "never"), Stage.BUILD),
    ("1- triage already done", p(triage=M, has_build=False), AUTO, Stage.BUILD),
    # rule 2: spec needed
    ("2+ size L reaches spec_min_size", p(triage=L, has_build=False), AUTO, Stage.SPEC),
    ("2+ ambiguity on a small ticket", p(triage=AMBIGUOUS_S, has_build=False), AUTO, Stage.SPEC),
    ("2+ always", p(has_build=False), Policy("never", "always"), Stage.SPEC),
    ("2- size M below L", p(triage=M, has_build=False), AUTO, Stage.BUILD),
    ("2- spec never", p(triage=L, has_build=False), Policy("auto", "never"), Stage.BUILD),
    # rules 3 and 4: the spec waits for /approve
    ("3+ spec with requested changes", p(triage=L, spec=SpecView("s", False, True), has_build=False), AUTO, Stage.SPEC),
    ("4+ spec not approved", p(triage=L, spec=SpecView("s", False, False), has_build=False), AUTO, Stage.AWAIT_APPROVAL),
    ("4- spec approved goes to build", p(triage=L, spec=SpecView("s", True, False), has_build=False), AUTO, Stage.BUILD),
    # rule 5: feedback on this commit
    ("5+ feedback on the head", p(feedback_sha="h", reviews=(Review("h", 0),)), Policy(), Stage.REWORK),
    ("5- feedback on an older commit", p(feedback_sha="old", reviews=(Review("h", 0),)), Policy(), Stage.PASS),
    # rule 6: build
    ("6+ no build commit yet", p(has_build=False), Policy(), Stage.BUILD),
    ("6+ head is a work in progress", p(head_complete=False), Policy(), Stage.BUILD),
    ("6- a complete build commit exists", p(), Policy(), Stage.REVIEW),
    # rule 7: review
    ("7+ no review for the head", p(reviews=(Review("other", 0),)), Policy(), Stage.REVIEW),
    ("7- reviewed", p(reviews=(Review("h", 0),)), Policy(), Stage.PASS),
    # rule 8: pass
    ("8+ last review has no must-fix", p(reviews=(Review("h", 1), Review("h", 0))), Policy(), Stage.PASS),
    ("8- last review has must-fix", p(reviews=(Review("h", 0), Review("h", 1))), Policy(), Stage.REWORK),
    # rule 9: blocked
    ("9+ too many failed rounds", p(reviews=(Review("a", 1), Review("b", 1), Review("h", 1))), Policy(), Stage.BLOCKED),
    ("9- two failed rounds are still allowed", p(reviews=(Review("a", 1), Review("h", 1))), Policy(), Stage.REWORK),
    # rule 10: rework
    ("10 rework after a review", p(reviews=(Review("h", 2),)), Policy(), Stage.REWORK),
]


@pytest.mark.parametrize(("name", "progress", "policy", "expected"), CASES, ids=[c[0] for c in CASES])
def test_the_stage_table(name, progress, policy, expected):
    assert stage(progress, policy) is expected


def test_without_a_policy_the_old_behaviour_holds():
    assert next_stage(Progress(False, "h", False, ()), 2) is Stage.BUILD
