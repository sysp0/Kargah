from datetime import UTC, datetime
from pathlib import Path

from kargah.adapters.fs_runstore import FsRunStore
from kargah.domain.pricing import ModelPrice
from kargah.orchestrator.recording import RecordingHarness
from kargah.ports.harness import HarnessRequest, HarnessResult


class Ws:
    root = Path("/ignored")

    def head(self):
        return "h" * 40

    def base_sha(self, base):
        return "b" * 40

    def diff(self, base):
        return "DIFF"


class Inner:
    name = "codex"

    def __init__(self, result):
        self.result = result

    def run(self, request):
        return self.result


def record_one(tmp_path, result, role="build", model="m", prices=None):
    store, sink = FsRunStore(tmp_path), []
    harness = RecordingHarness(Inner(result), store, prices or {}, lambda: datetime(2026, 1, 1, tzinfo=UTC), "r1", 7,
                               Ws(), "main", "TICKET", iter(range(1, 99)), sink)
    reply = harness.run(HarnessRequest(role, "PROMPT", tmp_path, 60, model))
    assert reply is result                        # the result passes through unchanged
    [rec] = store.steps()
    assert sink == [rec]
    return store, rec


def test_status_mapping(tmp_path):
    cases = [(HarnessResult(ok=True, text="fine"), "ok"),
             (HarnessResult(ok=True, text="hmm\nQUESTION: which one?"), "question"),
             (HarnessResult(ok=False, limited=True), "limit"),
             (HarnessResult(ok=False, stopped=True), "stopped"),
             (HarnessResult(ok=False, error="boom"), "failed")]
    for i, (result, status) in enumerate(cases):
        assert record_one(tmp_path / str(i), result)[1].status == status


def test_fields_artifacts_and_role_name(tmp_path):
    store, rec = record_one(tmp_path, HarnessResult(ok=True, text="REPLY", tokens_in=10, tokens_out=4, tokens_cached=2))
    assert (rec.step_id, rec.run, rec.ticket, rec.role, rec.harness, rec.model) == ("r1-01", "r1", 7, "implement",
                                                                                       "codex", "m")
    assert (rec.base_sha, rec.head_sha, rec.tokens_cached) == ("b" * 40, "h" * 40, 2)
    assert [store.artifact("r1-01", n) for n in ("prompt.md", "reply.md", "diff.patch", "ticket.md")] == \
        ["PROMPT", "REPLY", "DIFF", "TICKET"]


def test_the_review_step_stores_no_diff(tmp_path):
    store, rec = record_one(tmp_path, HarnessResult(ok=True, text="VERDICT: PASS"), role="review")
    assert rec.role == "review" and store.artifact("r1-01", "diff.patch") is None


def test_cost_reported_estimated_unknown(tmp_path):
    assert record_one(tmp_path / "a", HarnessResult(ok=True, cost_usd=0.2))[1].cost_source == "reported"
    prices = {"m": ModelPrice(2.0, 10.0, 0.5)}
    _, est = record_one(tmp_path / "b", HarnessResult(ok=True, tokens_in=1000, tokens_out=10), prices=prices)
    assert est.cost_source == "estimated" and est.cost_usd is not None
    _, unknown = record_one(tmp_path / "c", HarnessResult(ok=True, tokens_in=1000, tokens_out=10))
    assert (unknown.cost_usd, unknown.cost_source) == (None, "unknown")


def test_a_full_disk_never_breaks_the_run(tmp_path):
    class Broken:
        def save_step(self, record, artifacts):
            raise OSError("disk full")

    result = HarnessResult(ok=True, text="x")
    harness = RecordingHarness(Inner(result), Broken(), {}, lambda: datetime(2026, 1, 1, tzinfo=UTC), "r1", 7, Ws(),
                               "main", "T", iter(range(1, 9)), [])
    assert harness.run(HarnessRequest("build", "p", tmp_path, 60)) is result
