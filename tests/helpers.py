"""Shared helpers of the loop and builder tests: a plan folder `x`, a Feature on its branch, the fake tracker."""
import json

from conftest import git

from kargah import config, events
from kargah.feature import Feature

PLAN = """# Part 01: demo

## Packages

| Pn | Title | Depends | Touches | files | acceptance | Risk | You see |
|---|---|---|---|---|---|---|---|
| P1 | One | - | api:a | `src/a.py`, `tests/test_a.py` | test_a | low | a |
| P2 | Two | P1 | api:b | `src/b.py`, `tests/test_b.py` | test_b | low | b |
| P3 | Three | - | api:c | `src/c.py`, `tests/test_c.py` | test_c | low | c |
"""
PASS = {"verdict": "VERDICT: PASS\nCOMMIT: feat: done"}
FIX = {"verdict": "VERDICT: FIX\n1. src/a.py:1 - missing guard - add it"}
FOLDER = "docs/devchain-plan/x"
NOTE = f"{FOLDER}/blocked-P1.md"
PART = f"{FOLDER}/01-demo.md"


def work(name, text="x = 1\n"):
    return {"write": {f"src/{name}.py": text, f"tests/test_{name}.py": "def test_x():\n    assert True\n"}}


def setup(repo, plan=PLAN, toml=""):
    """Commit the plan folder on main (the plan branch starts from it) and an empty tracker."""
    folder = repo.root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "01-demo.md").write_text(plan)
    if toml:
        (repo.root / "devchain.toml").write_text((repo.root / "devchain.toml").read_text() + toml)
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "plan")
    git(repo.root, "push", "-q", "origin", "main")
    (repo.fake / "gh.json").write_text("[]")


def cfg_of(repo):
    return config.load(repo.root)


def feature(repo, planfix=False):
    """A Feature of plan x on the plan branch."""
    git(repo.root, "checkout", "-q", "-B", "plan/x", "origin/main")
    cfg = cfg_of(repo)
    if planfix:
        cfg.data["planfix"] = {"model": "fake-opus", "flags": "--effort medium"}
    run = events.create(cfg.runs_dir, "loop")
    return Feature(cfg, run, "x")


def states(feat, pkg="P1"):
    return [e["state"] for e in events.read(feat.run.events_path)[0] if e["type"] == "pkg" and e.get("pkg") == pkg]


def issues(repo):
    return {i["number"]: i for i in json.loads((repo.fake / "gh.json").read_text())}


def by_title(repo, prefix):
    return next(i for i in issues(repo).values() if i["title"].startswith(prefix))


def labels(issue):
    return {x["name"] for x in issue["labels"]}


def put_issue(repo, number, title, labels_=(), body="", comments=(), author="owner", state="OPEN"):
    data = json.loads((repo.fake / "gh.json").read_text())
    data.append({"number": number, "title": title, "body": body, "state": state, "url": f"u/{number}",
                 "author": {"login": author}, "labels": [{"name": n} for n in labels_],
                 "comments": [{"author": {"login": a}, "body": b} for a, b in comments]})
    (repo.fake / "gh.json").write_text(json.dumps(data))


def answer(repo, number, text, author="owner"):
    data = json.loads((repo.fake / "gh.json").read_text())
    next(i for i in data if i["number"] == number).setdefault("comments", []).append(
        {"author": {"login": author}, "body": text})
    (repo.fake / "gh.json").write_text(json.dumps(data))
