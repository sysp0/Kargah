from engine_fixtures import git, make_remote

from kargah.adapters.file_sources import DefaultBranchSource, DirSource
from kargah.adapters.git_workspace import GitWorkspace
from kargah.adapters.toml_config import load_project_config


def test_dir_source_reads_and_lists_files_on_disk(tmp_path):
    (tmp_path / ".kargah/agents/review").mkdir(parents=True)
    (tmp_path / ".kargah/agents/review/agent.md").write_text("x")
    (tmp_path / ".kargah/config.toml").write_text("[check]\ncommand = 'make'\n")
    src = DirSource(tmp_path)
    assert src.read(".kargah/missing") is None
    assert src.read(".kargah/agents/review/agent.md") == "x"
    assert src.list(".kargah") == [".kargah/agents/review/agent.md", ".kargah/config.toml"]
    assert src.list("nope") == []
    assert load_project_config(src).check_command == "make"


def test_default_branch_source_ignores_the_checked_out_ticket_branch(tmp_path):
    remote = make_remote(tmp_path)
    ws = GitWorkspace(tmp_path / "repo", str(remote), "x", ("bot", "b@b"))
    ws.prepare("kargah/1", "main")
    ws.write_file(".kargah/config.toml", '[check]\ncommand = "evil"\n')
    ws.write_file(".kargah/extra/new.md", "new")
    git(ws.root, "add", "-A")
    src = DefaultBranchSource(ws)
    assert "evil" not in (src.read(".kargah/config.toml") or "")
    assert src.list(".kargah") == [".kargah/config.toml"]
    assert src.read(".kargah/extra/new.md") is None
    assert load_project_config(src).check_command != "evil"


def test_default_branch_source_before_the_first_clone_is_empty(tmp_path):
    src = DefaultBranchSource(GitWorkspace(tmp_path / "repo", "unused", "x", ("bot", "b@b")))
    assert src.read(".kargah/config.toml") is None and src.list(".kargah") == []
