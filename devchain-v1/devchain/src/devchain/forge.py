"""The issue tracker is devchain's database: GitHub through `gh`, or GitLab through `glab` (setting forge.cli).

Every call is one CLI process and raises ForgeError on failure. `Tracker` is what the loop uses: one snapshot of the
issues per round, and writes that go through at once or wait in an outbox file while the tracker is down. A queued
write is applied to the snapshot too, so the loop's state never depends on whether GitHub was reachable.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from .config import Config

FIELDS = {"plan": "Plan", "part": "Part", "package": "Package", "kind": "Kind", "commit": "Tested commit",
          "steps": "Steps", "expected": "Expected", "actual": "Actual", "scenario": "Scenario",
          "seed": "Seed", "severity": "Severity", "related": "Related tasks"}
NO_ANSWER = "_No response_"


class ForgeError(Exception):
    pass


@dataclass
class Comment:
    author: str
    body: str
    created: str = ""


@dataclass
class Issue:
    number: int
    title: str
    body: str = ""
    url: str = ""
    author: str = ""
    state: str = "open"   # open | closed
    labels: set = field(default_factory=set)
    comments: list = field(default_factory=list)   # [Comment], oldest first

    @property
    def open(self) -> bool:
        return self.state == "open"

    @property
    def fields(self) -> dict:
        return parse_body(self.body)


def parse_body(body: str) -> dict:
    """{field: value} from an issue form body: "### Label" headings, each followed by its answer."""
    by_label = {label.lower(): key for key, label in FIELDS.items()}
    out, key, lines = {}, None, []
    for line in (body or "").splitlines() + ["### end"]:
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            if key:
                value = "\n".join(lines).strip()
                out[key] = "" if value == NO_ANSWER else value
            key, lines = by_label.get(m.group(1).lower().removesuffix(" (optional)")), []
        elif key:
            lines.append(line)
    return out


class Cli:
    """The CLI calls both trackers share; the subclasses map them to their commands."""

    name = ""

    def __init__(self, cfg: Config, binary: list[str]):
        self.cfg, self.bin = cfg, binary
        self.repo = str(cfg.get("forge.repo") or cfg.get("issues.repo") or cfg.get("git.github_repo") or "")
        self.limit = int(cfg.get("forge.limit", 300))

    def call(self, *args: str, stdin: str | None = None) -> str:
        try:
            proc = subprocess.run([*self.bin, *args], cwd=self.cfg.root, capture_output=True, text=True,
                                  input=stdin, timeout=int(self.cfg.get("forge.timeout_seconds", 60)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ForgeError(f"{self.name}: {exc}") from exc
        if proc.returncode != 0:
            raise ForgeError(f"{self.name}: " + ((proc.stderr or proc.stdout).strip()[-300:] or
                                                f"exit {proc.returncode}"))
        return proc.stdout

    def load(self, out: str) -> object:
        try:
            return json.loads(out or "null")
        except json.JSONDecodeError as exc:
            raise ForgeError(f"{self.name}: unreadable output: {exc}") from exc


class GhCli(Cli):
    name = "gh"

    def repo_args(self) -> list[str]:
        return ["--repo", self.repo] if self.repo else []

    def issues(self, label: str | None = None, state: str = "all") -> list[Issue]:
        args = ["issue", "list", "--state", state, "--limit", str(self.limit),
                "--json", "number,title,url,author,state,labels,body,comments", *self.repo_args()]
        if label:
            args += ["--label", label]
        found = self.load(self.call(*args)) or []
        try:
            return [Issue(number=int(i["number"]), title=i.get("title", ""), body=i.get("body") or "",
                          url=i.get("url", ""), author=(i.get("author") or {}).get("login", ""),
                          state=str(i.get("state", "OPEN")).lower(),
                          labels={x.get("name", "") for x in i.get("labels") or []},
                          comments=[Comment((c.get("author") or {}).get("login", ""), c.get("body") or "",
                                            c.get("createdAt", "")) for c in i.get("comments") or []])
                    for i in found]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ForgeError(f"gh: unreadable issue list: {exc}") from exc

    def create(self, title: str, body: str, labels: list[str]) -> int:
        args = ["issue", "create", "--title", title, "--body-file", "-", *self.repo_args()]
        for name in labels:
            args += ["--label", name]
        out = self.call(*args, stdin=body).strip()
        m = re.search(r"/issues/(\d+)\s*$", out)
        if not m:
            raise ForgeError(f"gh: no issue number in {out[-200:]!r}")
        return int(m.group(1))

    def edit_body(self, number: int, body: str) -> None:
        self.call("issue", "edit", str(number), "--body-file", "-", *self.repo_args(), stdin=body)

    def comment(self, number: int, body: str) -> None:
        self.call("issue", "comment", str(number), "--body-file", "-", *self.repo_args(), stdin=body)

    def labels(self, number: int, add: tuple = (), remove: tuple = ()) -> None:
        args = ["issue", "edit", str(number), *self.repo_args()]
        for name in add:
            args += ["--add-label", name]
        for name in remove:
            args += ["--remove-label", name]
        if add or remove:
            self.call(*args)

    def ensure_labels(self, labels: dict[str, str]) -> None:
        for name, color in labels.items():
            self.call("label", "create", name, "--color", color, "--force", *self.repo_args())

    def link_blocked_by(self, number: int, blocker: int, on: bool = True) -> None:
        """GitHub issue dependencies; raises ForgeError where the repo or the gh version has none."""
        repo = self.repo or "{owner}/{repo}"
        blocker_id = self.call("api", f"repos/{repo}/issues/{blocker}", "--jq", ".id").strip()
        if on:
            self.call("api", "-X", "POST", f"repos/{repo}/issues/{number}/dependencies/blocked_by",
                      "-F", f"issue_id={blocker_id}")
        else:
            self.call("api", "-X", "DELETE", f"repos/{repo}/issues/{number}/dependencies/blocked_by/{blocker_id}")


class GlabCli(Cli):
    """GitLab REST through `glab api`: iid is the issue number, notes are the comments."""

    name = "glab"

    def __init__(self, cfg: Config, binary: list[str]):
        super().__init__(cfg, binary)
        self.project = f"projects/{quote(self.repo, safe='')}" if self.repo else "projects/:id"
        self.notes: dict[int, tuple[str, list]] = {}   # iid -> (updated_at, comments): notes cost one call each

    def api(self, method: str, path: str, data: dict | None = None) -> object:
        args = ["api", "--method", method, f"{self.project}/{path}"]
        if data is not None:
            args += ["--header", "Content-Type: application/json", "--input", "-"]
        return self.load(self.call(*args, stdin=json.dumps(data) if data is not None else None))

    def issues(self, label: str | None = None, state: str = "all") -> list[Issue]:
        query = f"issues?state={'opened' if state == 'open' else state}&per_page=100&order_by=created_at"
        if label:
            query += f"&labels={quote(label, safe='')}"
        found = []
        for page in range(1, max(1, self.limit // 100) + 1):
            batch = self.api("GET", f"{query}&page={page}") or []
            found += batch
            if len(batch) < 100:
                break
        out = []
        try:
            for i in found:
                iid = int(i["iid"])
                updated = str(i.get("updated_at", ""))
                if self.notes.get(iid, ("", []))[0] != updated:
                    notes = self.api("GET", f"issues/{iid}/notes?sort=asc&per_page=100") or []
                    self.notes[iid] = (updated, [Comment((n.get("author") or {}).get("username", ""),
                                                         n.get("body") or "", n.get("created_at", ""))
                                                 for n in notes if not n.get("system")])
                out.append(Issue(number=iid, title=i.get("title", ""), body=i.get("description") or "",
                                 url=i.get("web_url", ""), author=(i.get("author") or {}).get("username", ""),
                                 state="open" if i.get("state") == "opened" else "closed",
                                 labels=set(i.get("labels") or []), comments=list(self.notes[iid][1])))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ForgeError(f"glab: unreadable issue list: {exc}") from exc
        return out

    def create(self, title: str, body: str, labels: list[str]) -> int:
        made = self.api("POST", "issues", {"title": title, "description": body, "labels": ",".join(labels)})
        try:
            return int(made["iid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ForgeError(f"glab: no issue number in {str(made)[:200]}") from exc

    def edit_body(self, number: int, body: str) -> None:
        self.api("PUT", f"issues/{number}", {"description": body})

    def comment(self, number: int, body: str) -> None:
        self.api("POST", f"issues/{number}/notes", {"body": body})

    def labels(self, number: int, add: tuple = (), remove: tuple = ()) -> None:
        if add or remove:
            self.api("PUT", f"issues/{number}", {"add_labels": ",".join(add), "remove_labels": ",".join(remove)})

    def ensure_labels(self, labels: dict[str, str]) -> None:
        have = {x.get("name") for x in self.api("GET", "labels?per_page=100") or []}
        for name, color in labels.items():
            if name not in have:
                self.api("POST", "labels", {"name": name, "color": f"#{color}"})

    def link_blocked_by(self, number: int, blocker: int, on: bool = True) -> None:
        """GitLab linked issues (`is_blocked_by` needs a paid tier); raises ForgeError where it is missing."""
        if on:
            self.api("POST", f"issues/{number}/links", {"target_project_id": self.repo or ":id",
                                                         "target_issue_iid": str(blocker),
                                                         "link_type": "is_blocked_by"})
            return
        for link in self.api("GET", f"issues/{number}/links") or []:
            if int(link.get("iid", 0)) == blocker and link.get("issue_link_id"):
                self.api("DELETE", f"issues/{number}/links/{link['issue_link_id']}")


def cli(cfg: Config) -> Cli:
    kind = str(cfg.get("forge.cli", "gh"))
    if kind == "glab":
        return GlabCli(cfg, cfg.glab_bin())
    if kind == "gh":
        return GhCli(cfg, cfg.gh_bin())
    raise ForgeError(f"forge.cli is {kind!r}; use gh or glab")


class Tracker:
    """The loop's view of the tracker: a snapshot per round, writes through an outbox when the tracker is down."""

    def __init__(self, cfg: Config, outbox: Path, journal=None):
        self.cfg, self.cli, self.outbox, self.journal = cfg, cli(cfg), outbox, journal
        self.snapshot: dict[int, Issue] = {}
        self.error = ""        # why the last read or write failed; "" when the tracker answered
        self.linking = True    # set False after the first failed blocked-by link: the tracker has no such links

    # ---- reads -------------------------------------------------------------------------------------------------
    def refresh(self, label: str) -> bool:
        """Send the queued writes, then read the issues with this label and every open issue. False when the
        tracker is down (the last snapshot stays, with the queued writes applied)."""
        self.flush()
        try:
            found = {i.number: i for i in self.cli.issues(label=label, state="all")}
            found.update({i.number: i for i in self.cli.issues(state="open") if i.number not in found})
        except ForgeError as exc:
            self.fail(exc)
            return False
        self.error = ""
        self.snapshot = found
        for op in self.pending():
            self.apply(op)
        return True

    def issues(self) -> list[Issue]:
        return sorted(self.snapshot.values(), key=lambda i: i.number)

    def get(self, number: int) -> Issue | None:
        return self.snapshot.get(number)

    # ---- writes ------------------------------------------------------------------------------------------------
    def create(self, title: str, body: str, labels: list[str]) -> int | None:
        """The new issue's number, or None when the tracker is down (the caller tries again next round)."""
        try:
            number = self.cli.create(title, body, labels)
        except ForgeError as exc:
            self.fail(exc)
            return None
        self.snapshot[number] = Issue(number=number, title=title, body=body, labels=set(labels))
        return number

    def comment(self, number: int, body: str) -> None:
        self.write({"op": "comment", "number": number, "body": body})

    def edit_body(self, number: int, body: str) -> None:
        self.write({"op": "edit_body", "number": number, "body": body})

    def labels(self, number: int, add: tuple = (), remove: tuple = ()) -> None:
        issue = self.snapshot.get(number)
        have = issue.labels if issue else set()
        add = tuple(x for x in add if x not in have)
        remove = tuple(x for x in remove if x in have)
        if add or remove:
            self.write({"op": "labels", "number": number, "add": list(add), "remove": list(remove)})

    def ensure_labels(self, labels: dict[str, str]) -> bool:
        try:
            self.cli.ensure_labels(labels)
        except ForgeError as exc:
            self.fail(exc)
            return False
        return True

    def link_blocked_by(self, number: int, blocker: int, on: bool = True) -> None:
        """Best effort: the text reference (#n in a comment) is the link that always works."""
        if not self.linking:
            return
        try:
            self.cli.link_blocked_by(number, blocker, on)
        except ForgeError as exc:
            self.linking = False
            self.note(f"blocked-by links are not available ({exc}); the #n references in the comments link the "
                      "issues")

    # ---- outbox ------------------------------------------------------------------------------------------------
    def write(self, op: dict) -> None:
        if self.pending():   # keep the order: nothing passes a queued write
            self.queue(op)
            return
        try:
            self.send(op)
        except ForgeError as exc:
            self.fail(exc)
            self.queue(op)
            return
        self.apply(op)

    def send(self, op: dict) -> None:
        if op["op"] == "comment":
            self.cli.comment(op["number"], op["body"])
        elif op["op"] == "edit_body":
            self.cli.edit_body(op["number"], op["body"])
        elif op["op"] == "labels":
            self.cli.labels(op["number"], tuple(op["add"]), tuple(op["remove"]))

    def apply(self, op: dict) -> None:
        issue = self.snapshot.get(op["number"])
        if issue is None:
            return
        if op["op"] == "comment":
            issue.comments.append(Comment("devchain", op["body"]))
        elif op["op"] == "edit_body":
            issue.body = op["body"]
        elif op["op"] == "labels":
            issue.labels = (issue.labels - set(op["remove"])) | set(op["add"])

    def pending(self) -> list[dict]:
        if not self.outbox.is_file():
            return []
        return [json.loads(line) for line in self.outbox.read_text(encoding="utf-8").splitlines() if line.strip()]

    def queue(self, op: dict) -> None:
        self.outbox.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(op, ensure_ascii=False) + "\n")
        self.apply(op)

    def flush(self) -> None:
        ops = self.pending()
        for i, op in enumerate(ops):
            try:
                self.send(op)
            except ForgeError as exc:
                self.fail(exc)
                rest = ops[i:]
                self.outbox.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rest),
                                       encoding="utf-8")
                return
        if ops:
            self.outbox.unlink(missing_ok=True)
            self.note(f"sent {len(ops)} queued tracker writes")

    def fail(self, exc: Exception) -> None:
        if str(exc) != self.error:
            self.note(f"tracker unavailable: {exc}")
        self.error = str(exc)

    def note(self, text: str) -> None:
        if self.journal:
            self.journal.decision("tracker", "-", text)
