"""The Tracker port on GitLab issues."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from kargah.adapters.gitlab.paging import pages
from kargah.domain.ticket import Author, Comment, Ticket
from kargah.ports.http import HttpClient


class GitLabTracker:
    def __init__(self, http: HttpClient, project: str) -> None:
        self._http = http
        self._base = f"projects/{quote(project, safe='')}"

    def whoami(self) -> Author:
        return _author(self._http.request("GET", "user"))

    def tickets_with_label(self, label: str, include_closed: bool = False) -> list[Ticket]:
        state = "all" if include_closed else "opened"
        rows = pages(self._http, f"{self._base}/issues", {"labels": label, "state": state, "order_by": "created_at",
                                                          "sort": "asc"})
        return [_ticket(r) for r in rows]

    def get_ticket(self, number: int) -> Ticket:
        return _ticket(self._http.request("GET", f"{self._base}/issues/{number}"))

    def comments(self, number: int) -> list[Comment]:
        rows = pages(self._http, f"{self._base}/issues/{number}/notes", {"sort": "asc", "order_by": "created_at"})
        return [_comment(r) for r in rows if not r.get("system")]

    def post_comment(self, number: int, body: str) -> Comment:
        return _comment(self._http.request("POST", f"{self._base}/issues/{number}/notes", json={"body": body}))

    def add_label(self, number: int, label: str) -> None:
        self._http.request("PUT", f"{self._base}/issues/{number}", json={"add_labels": label})

    def remove_label(self, number: int, label: str) -> None:
        self._http.request("PUT", f"{self._base}/issues/{number}", json={"remove_labels": label})

    def create_ticket(self, title: str, body: str, labels: tuple[str, ...]) -> int:
        row = self._http.request("POST", f"{self._base}/issues",
                                 json={"title": title, "description": body, "labels": ",".join(labels)})
        return int(row["iid"])

    def close_ticket(self, number: int) -> None:
        self._http.request("PUT", f"{self._base}/issues/{number}", json={"state_event": "close"})


def _author(row: dict[str, Any]) -> Author:
    return Author(id=row["id"], username=row["username"])


def _ticket(row: dict[str, Any]) -> Ticket:
    return Ticket(number=row["iid"], title=row["title"], body=row.get("description") or "",
                  labels=frozenset(row.get("labels", [])), open=row.get("state", "opened") == "opened",
                  url=row.get("web_url", ""))


def _comment(row: dict[str, Any]) -> Comment:
    return Comment(id=row["id"], author=_author(row["author"]), body=row["body"],
                   created_at=datetime.fromisoformat(row["created_at"]))
