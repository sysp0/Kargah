#!/usr/bin/env python3
"""Fake `glab api`: the GitLab REST calls devchain makes, on the same $FAKE_DIR/gh.json as fake_gh.py."""
import json
import os
import re
import sys
from pathlib import Path

state = Path(os.environ["FAKE_DIR"])
args = sys.argv[1:]
data = json.loads(sys.stdin.read() or "null") if "--input" in args else None
with (state / "glab-calls.jsonl").open("a") as fh:
    fh.write(json.dumps(args) + "\n")
if (state / "gh.fail").exists():
    print("glab: not logged in", file=sys.stderr)
    sys.exit(1)
path = state / "gh.json"
issues = json.loads(path.read_text()) if path.exists() else []
method = args[args.index("--method") + 1]
url = next(a for a in args[1:] if a.startswith("projects/"))
route, _, query = url.partition("?")
params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
route = re.sub(r"^projects/[^/]+/", "", route)


def out(value):
    print(json.dumps(value))


def gitlab(i):
    return {"iid": i["number"], "title": i["title"], "description": i.get("body", ""),
            "state": "opened" if i.get("state", "OPEN") == "OPEN" else "closed",
            "labels": [x["name"] for x in i.get("labels", [])], "author": {"username": i["author"]["login"]},
            "web_url": i.get("url", ""), "updated_at": json.dumps(i)}


def find(iid):
    return next(i for i in issues if i["number"] == int(iid))


if method == "GET" and route == "issues":
    found = issues
    if params.get("labels"):
        found = [i for i in found if any(x["name"] == params["labels"].replace("%3A", ":") for x in i["labels"])]
    if params.get("state") == "opened":
        found = [i for i in found if i.get("state", "OPEN") == "OPEN"]
    out([gitlab(i) for i in found] if params.get("page", "1") == "1" else [])
elif method == "GET" and (m := re.match(r"issues/(\d+)/notes$", route)):
    out([{"author": {"username": c["author"]["login"]}, "body": c["body"], "system": False}
         for c in find(m.group(1)).get("comments", [])] + [{"author": {"username": "x"}, "body": "x", "system": True}])
elif method == "POST" and route == "issues":
    number = max([i["number"] for i in issues] + [0]) + 1
    issues.append({"number": number, "title": data["title"], "body": data["description"], "state": "OPEN",
                   "author": {"login": "devchain"}, "url": f"https://gitlab.test/acme/repo/-/issues/{number}",
                   "labels": [{"name": n} for n in data["labels"].split(",") if n], "comments": []})
    path.write_text(json.dumps(issues))
    out({"iid": number})
elif method == "PUT" and (m := re.match(r"issues/(\d+)$", route)):
    issue = find(m.group(1))
    if "description" in data:
        issue["body"] = data["description"]
    names = [x["name"] for x in issue["labels"]]
    remove = [n for n in data.get("remove_labels", "").split(",") if n]
    names = [n for n in names if n not in remove] + [n for n in data.get("add_labels", "").split(",") if n]
    issue["labels"] = [{"name": n} for n in dict.fromkeys(names)]
    path.write_text(json.dumps(issues))
    out(gitlab(issue))
elif method == "POST" and (m := re.match(r"issues/(\d+)/notes$", route)):
    find(m.group(1)).setdefault("comments", []).append({"author": {"login": "devchain"}, "body": data["body"]})
    path.write_text(json.dumps(issues))
    out({"id": 1})
elif route.startswith("labels"):
    out([])
elif "/links" in route:
    with (state / "glab-links.jsonl").open("a") as fh:
        fh.write(json.dumps([method, route, data]) + "\n")
    out([])
else:
    print(f"fake glab: unknown call {method} {route}", file=sys.stderr)
    sys.exit(2)
