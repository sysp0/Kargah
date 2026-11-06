import json

from engine_fixtures import git, make_remote

from kargah.adapters.codex import _usage
from kargah.adapters.git_workspace import GitWorkspace


def test_diff_and_base_sha_include_untracked_files(tmp_path):
    remote = make_remote(tmp_path)
    ws = GitWorkspace(tmp_path / "repo", str(remote), "x", ("bot", "b@b"))
    ws.prepare("kargah/1", "main")
    assert ws.base_sha("main") == git(ws.root, "rev-parse", "origin/main")
    ws.write_file("new.txt", "hello\n")
    assert "+hello" in ws.diff("main")


def test_diff_is_cut_to_the_limit(tmp_path, monkeypatch):
    remote = make_remote(tmp_path)
    ws = GitWorkspace(tmp_path / "repo", str(remote), "x", ("bot", "b@b"))
    ws.prepare("kargah/1", "main")
    ws.write_file("big.txt", "x" * 500)
    monkeypatch.setattr("kargah.adapters.git_workspace.MAX_DIFF_CHARS", 100)
    assert len(ws.diff("main")) == 100


def test_codex_usage_reads_cached_tokens():
    event = {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 6, "output_tokens": 2}}
    assert _usage(json.dumps(event)) == (10, 2, 6)
    assert _usage("not json") == (None, None, None)


def test_task_commits_read_the_trailers_newest_first(tmp_path):
    remote = make_remote(tmp_path)
    ws = GitWorkspace(tmp_path / "repo", str(remote), "x", ("bot", "b@b"))
    ws.prepare("kargah/1", "main")
    assert ws.task_commits("main") == []
    ws.write_file("a.txt", "1")
    first = ws.commit("spec", {"Kargah-Task": "spec", "Kargah-State": "complete"})
    ws.write_file("a.txt", "2")
    second = ws.commit("wip", {"Kargah-Task": "build", "Kargah-State": "incomplete"})
    ws.write_file("a.txt", "3")
    third = ws.commit("plain", {})
    assert ws.task_commits("main") == [(third, "", ""), (second, "build", "incomplete"), (first, "spec", "complete")]
