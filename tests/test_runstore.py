import stat
from datetime import UTC, datetime

import pytest

from kargah.adapters.fs_runstore import FsRunStore
from kargah.domain.records import StepRecord


def record(step_id="r1-01", started="2026-01-01T12:00:00+00:00", **kw):
    base = dict(step_id=step_id, run=step_id.rsplit("-", 1)[0], ticket=7, role="implement", harness="codex", model="",
                started=started, seconds=1.5, status="ok", tokens_in=10, tokens_out=5, tokens_cached=None,
                cost_usd=None, cost_source="unknown", base_sha="b" * 40, head_sha="h" * 40)
    return StepRecord(**{**base, **kw})


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_layout_and_permissions(tmp_path):
    store = FsRunStore(tmp_path)
    store.save_step(record(), {"prompt.md": "P", "reply.md": "R", "diff.patch": "D", "ticket.md": "T"})
    folder = tmp_path / "runs/r1/r1-01"
    assert sorted(p.name for p in folder.iterdir()) == ["diff.patch", "prompt.md", "reply.md", "ticket.md"]
    assert mode(folder) == 0o700 and mode(tmp_path / "runs") == 0o700 and mode(folder.parent) == 0o700
    assert mode(folder / "prompt.md") == 0o600 and mode(tmp_path / "steps.jsonl") == 0o600


def test_records_round_trip_and_append_in_order(tmp_path):
    store = FsRunStore(tmp_path)
    first, second = record("r1-01"), record("r1-02", cost_usd=0.5, cost_source="reported", role="review")
    store.save_step(first, {})
    store.save_step(second, {})
    assert store.steps() == [first, second]
    assert len((tmp_path / "steps.jsonl").read_text().splitlines()) == 2
    assert FsRunStore(tmp_path / "other").steps() == []


def test_artifact_returns_text_or_none(tmp_path):
    store = FsRunStore(tmp_path)
    store.save_step(record(), {"prompt.md": "hello"})
    assert store.artifact("r1-01", "prompt.md") == "hello"
    assert store.artifact("r1-01", "nope.md") is None
    assert store.artifact("r9-01", "prompt.md") is None


def test_unsafe_names_are_refused(tmp_path):
    store = FsRunStore(tmp_path)
    with pytest.raises(ValueError):
        store.save_step(record(), {"../x": "bad"})


def test_prune_removes_old_folders_but_keeps_the_jsonl_lines(tmp_path):
    store = FsRunStore(tmp_path)
    store.save_step(record("old-01", started="2025-01-01T00:00:00+00:00"), {"reply.md": "x"})
    store.save_step(record("new-01", started="2026-06-01T00:00:00+00:00"), {"reply.md": "y"})
    assert store.prune(datetime(2026, 1, 1, tzinfo=UTC)) == 1
    assert not (tmp_path / "runs/old").exists() and (tmp_path / "runs/new/new-01/reply.md").exists()
    assert len(store.steps()) == 2 and store.artifact("old-01", "reply.md") is None
    assert store.prune(datetime(2026, 1, 1, tzinfo=UTC)) == 0
