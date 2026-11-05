import json

import pytest

from kargah import config, forge


def issue(number, title="t", labels=(), comments=(), state="OPEN", body=""):
    return {"number": number, "title": title, "body": body, "state": state, "author": {"login": "owner"},
            "url": f"https://x/issues/{number}", "labels": [{"name": n} for n in labels],
            "comments": [{"author": {"login": a}, "body": b} for a, b in comments]}


def store(repo, *items):
    (repo.fake / "gh.json").write_text(json.dumps(list(items)))


def stored(repo):
    return {i["number"]: i for i in json.loads((repo.fake / "gh.json").read_text())}


def tool(repo, kind):
    cfg = config.load(repo.root)
    cfg.data["forge"] = {"cli": kind}
    return forge.cli(cfg)


@pytest.mark.parametrize("kind", ["gh", "glab"])
def test_both_trackers_read_and_write_the_same_issues(repo, kind):
    store(repo, issue(1, "P1: one", ["task", "plan:x"], [("owner", "hello")]), issue(2, "bug", ["feedback"],
                                                                                    state="CLOSED"))
    cli = tool(repo, kind)
    found = {i.number: i for i in cli.issues(label="plan:x")}
    assert list(found) == [1]
    assert found[1].labels == {"task", "plan:x"} and found[1].open
    assert [(c.author, c.body) for c in found[1].comments] == [("owner", "hello")]   # GitLab system notes dropped
    assert {i.number for i in cli.issues(state="open")} == {1}
    assert {i.number: i.state for i in cli.issues()} == {1: "open", 2: "closed"}

    number = cli.create("P2: two", "line one\n| a | b |\n<!-- devchain:task id=P2 -->", ["task", "plan:x"])
    cli.comment(number, "a comment with `code` and\nlines")
    cli.labels(number, add=("held",), remove=("task",))
    cli.edit_body(1, "new body")
    after = stored(repo)
    assert after[number]["body"].endswith("<!-- devchain:task id=P2 -->")
    assert [x["name"] for x in after[number]["labels"]] == ["plan:x", "held"]
    assert after[number]["comments"][-1]["body"] == "a comment with `code` and\nlines"
    assert after[1]["body"] == "new body"


def test_gh_passes_the_repo_and_sends_long_text_on_stdin(repo):
    store(repo, issue(1))
    cli = tool(repo, "gh")
    cli.comment(1, "x" * 50000)
    call = json.loads((repo.fake / "gh-calls.jsonl").read_text().splitlines()[-1])
    assert call == ["issue", "comment", "1", "--body-file", "-", "--repo", "acme/repo"]
    assert stored(repo)[1]["comments"][-1]["body"] == "x" * 50000


def test_a_failing_tracker_raises_forge_error(repo):
    (repo.fake / "gh.fail").write_text("")
    with pytest.raises(forge.ForgeError, match="not logged in"):
        tool(repo, "gh").issues()


def test_form_fields_are_read_from_the_body():
    body = "### Plan\n\nx\n\n### Steps\n\n1. open\n2. click\n\n### Seed (optional)\n\n_No response_\n"
    assert forge.parse_body(body) == {"plan": "x", "steps": "1. open\n2. click", "seed": ""}


def tracker(repo, tmp_path):
    cfg = config.load(repo.root)
    return forge.Tracker(cfg, tmp_path / "outbox.jsonl")


def test_writes_wait_in_the_outbox_while_the_tracker_is_down_and_go_out_in_order(repo, tmp_path):
    store(repo, issue(1, "P1: one", ["task", "plan:x"]))
    t = tracker(repo, tmp_path)
    assert t.refresh("plan:x")
    (repo.fake / "gh.fail").write_text("")
    t.comment(1, "first")
    t.labels(1, add=("held",))
    assert "not logged in" in t.error
    assert [c.body for c in t.get(1).comments] == ["first"]          # the snapshot has the queued writes
    assert "held" in t.get(1).labels
    assert not t.refresh("plan:x")                                   # down: the old snapshot stays
    assert [c.body for c in t.get(1).comments] == ["first"]
    assert t.create("P2: two", "b", ["task"]) is None                # a create is not queued: the next round tries
    (repo.fake / "gh.fail").unlink()
    t.comment(1, "second")                                           # waits behind the queued ones
    assert t.refresh("plan:x")
    assert [c["body"] for c in stored(repo)[1]["comments"]] == ["first", "second"]
    assert [x["name"] for x in stored(repo)[1]["labels"]] == ["task", "plan:x", "held"]
    assert not (tmp_path / "outbox.jsonl").exists() and t.error == ""


def test_label_writes_are_skipped_when_the_snapshot_has_them(repo, tmp_path):
    store(repo, issue(1, labels=["task"]))
    t = tracker(repo, tmp_path)
    t.refresh("task")
    before = len((repo.fake / "gh-calls.jsonl").read_text().splitlines())
    t.labels(1, add=("task",), remove=("held",))
    assert len((repo.fake / "gh-calls.jsonl").read_text().splitlines()) == before


def test_blocked_by_links_are_best_effort(repo, tmp_path):
    store(repo, issue(1), issue(2))
    t = tracker(repo, tmp_path)
    t.link_blocked_by(2, 1)
    assert "issues/2/dependencies/blocked_by" in (repo.fake / "gh-links.jsonl").read_text()
    (repo.fake / "gh.links.fail").write_text("")
    t.link_blocked_by(2, 1, on=False)
    assert not t.linking
    t.link_blocked_by(2, 1)   # no more calls once the tracker said it has no such links
    assert len((repo.fake / "gh-links.jsonl").read_text().splitlines()) == 1
