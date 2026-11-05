#!/usr/bin/env python3
"""Fake `gh`: issues in $FAKE_DIR/gh.json (gh's JSON shape); every call is logged to gh-calls.jsonl.

gh.fail makes every call fail (not logged in); gh.links.fail makes the issue-dependency API fail."""
import json
import os
import sys
from pathlib import Path

state = Path(os.environ["FAKE_DIR"])
args = sys.argv[1:]
body_in = sys.stdin.read() if "-" in args and "--body-file" in args else None
with (state / "gh-calls.jsonl").open("a") as fh:
    fh.write(json.dumps(args) + "\n")
if (state / "gh.fail").exists():
    print("gh: not logged in", file=sys.stderr)
    sys.exit(1)
path = state / "gh.json"
issues = json.loads(path.read_text()) if path.exists() else []


def value(flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag]


def save():
    path.write_text(json.dumps(issues))


def find(number):
    return next(i for i in issues if i["number"] == int(number))


def body():
    return body_in if body_in is not None else value("--body")[0]


if args[:2] == ["issue", "list"]:
    found = issues
    for label in value("--label"):
        found = [i for i in found if any(x["name"] == label for x in i.get("labels", []))]
    if value("--state") == ["open"]:
        found = [i for i in found if i.get("state", "OPEN") == "OPEN"]
    print(json.dumps(sorted(found, key=lambda i: -i["number"])))
elif args[:2] == ["issue", "create"]:
    number = max([i["number"] for i in issues] + [0]) + 1
    issues.append({"number": number, "title": value("--title")[0], "body": body(), "state": "OPEN",
                   "author": {"login": "devchain"}, "url": f"https://github.com/acme/repo/issues/{number}",
                   "labels": [{"name": n} for n in value("--label")], "comments": []})
    save()
    print(f"https://github.com/acme/repo/issues/{number}")
elif args[:2] == ["issue", "edit"]:
    issue = find(args[2])
    if "--body-file" in args or "--body" in args:
        issue["body"] = body()
    names = [x["name"] for x in issue.get("labels", [])]
    names = [n for n in names if n not in value("--remove-label")] + value("--add-label")
    issue["labels"] = [{"name": n} for n in dict.fromkeys(names)]
    save()
elif args[:2] == ["issue", "comment"]:
    find(args[2]).setdefault("comments", []).append({"author": {"login": "devchain"}, "body": body()})
    save()
elif args[:2] == ["label", "create"]:
    pass
elif args[:1] == ["api"]:
    if (state / "gh.links.fail").exists():
        print("gh: HTTP 404: Not Found", file=sys.stderr)
        sys.exit(1)
    if "--jq" in args:
        print(1000 + int(args[1].rsplit("/", 1)[1]))
    else:
        with (state / "gh-links.jsonl").open("a") as fh:
            fh.write(json.dumps(args) + "\n")
else:
    print(f"fake gh: unknown call {args}", file=sys.stderr)
    sys.exit(2)
