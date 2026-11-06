"""Merge requests on GitLab."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from kargah.adapters.gitlab.paging import pages
from kargah.domain.ticket import Author, Comment
from kargah.errors import TrackerError
from kargah.ports.githost import Discussion, MrView
from kargah.ports.http import HttpClient

DRAFT = "Draft: "


class GitLabHost:
    def __init__(self, http: HttpClient, project: str, web_url: str) -> None:
        self._http = http
        self._base = f"projects/{quote(project, safe='')}/merge_requests"
        self._web = web_url
        self._bot_id: int | None = None

    def ensure_draft_mr(self, branch: str, base: str, title: str, description: str) -> str:
        if mr := self._find(branch):
            return mr["web_url"]
        mr = self._http.request("POST", self._base, json={"source_branch": branch, "target_branch": base,
                                                          "title": DRAFT + title, "description": description,
                                                          "remove_source_branch": True})
        return mr["web_url"]

    def mark_ready(self, branch: str) -> None:
        mr = self._find(branch)
        if mr is None:
            raise TrackerError(f"no merge request for branch {branch}")
        title = mr["title"].removeprefix(DRAFT).removeprefix("Draft:").strip()
        self._http.request("PUT", f"{self._base}/{mr['iid']}", json={"title": title})

    def find_mr(self, branch: str) -> MrView | None:
        rows = self._http.request("GET", self._base, params={"source_branch": branch, "state": "all",
                                                             "order_by": "created_at", "sort": "desc"})
        if not rows:
            return None
        r = rows[0]
        return MrView(r["iid"], r["web_url"], r["state"], _time(r["created_at"]), _time(r.get("merged_at")))

    def open_discussions(self, branch: str) -> list[Discussion]:
        mr, bot = self._require(branch), self._me()
        found = []
        for row in pages(self._http, f"{self._base}/{mr['iid']}/discussions", {}):
            first = row["notes"][0]
            if not first.get("resolvable") or first.get("resolved") or first["author"]["id"] == bot:
                continue
            pos = first.get("position") or {}
            found.append(Discussion(row["id"], Author(first["author"]["id"], first["author"]["username"]),
                                    first["body"], pos.get("new_path"), pos.get("new_line"),
                                    _time(first["created_at"])))
        return found

    def resolve_discussion(self, branch: str, discussion_id: str, reply: str) -> None:
        iid = self._require(branch)["iid"]
        self._http.request("POST", f"{self._base}/{iid}/discussions/{discussion_id}/notes", json={"body": reply})
        self._http.request("PUT", f"{self._base}/{iid}/discussions/{discussion_id}", json={"resolved": True})

    def mr_notes(self, branch: str) -> list[Comment]:
        mr = self._find_any(branch)
        if mr is None:
            return []
        rows = pages(self._http, f"{self._base}/{mr['iid']}/notes", {"sort": "asc", "order_by": "created_at"})
        return [Comment(r["id"], Author(r["author"]["id"], r["author"]["username"]), r["body"],
                        _time(r["created_at"])) for r in rows if not r.get("system")]

    def commit_authors(self, branch: str) -> list[str]:
        mr = self._find_any(branch)
        if mr is None:
            return []
        return [c["author_email"] for c in pages(self._http, f"{self._base}/{mr['iid']}/commits", {})]

    def _find(self, branch: str) -> dict | None:
        rows = self._http.request("GET", self._base, params={"source_branch": branch, "state": "opened"})
        return rows[0] if rows else None

    def _find_any(self, branch: str) -> dict | None:
        rows = self._http.request("GET", self._base, params={"source_branch": branch, "state": "all",
                                                             "order_by": "created_at", "sort": "desc"})
        return rows[0] if rows else None

    def _require(self, branch: str) -> dict:
        mr = self._find_any(branch)
        if mr is None:
            raise TrackerError(f"no merge request for branch {branch}")
        return mr

    def _me(self) -> int:
        if self._bot_id is None:
            self._bot_id = self._http.request("GET", "user")["id"]
        return self._bot_id


def _time(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
