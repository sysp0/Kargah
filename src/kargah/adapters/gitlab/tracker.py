"""The Tracker port on GitLab issues."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from kargah.domain.ticket import Author, Comment, Ticket
from kargah.ports.http import HttpClient

PAGE = 100


class GitLabTracker:
    def __init__(self, http: HttpClient, project: str) -> None:
        self._http = http
        self._base = f"projects/{quote(project, safe='')}"

    def whoami(self) -> Author:
        return _author(self._http.request("GET", "user"))

    def tickets_with_label(self, label: str) -> list[Ticket]:
        rows = self._pages(f"{self._base}/issues", {"labels": label, "state": "opened", "order_by": "created_at",
                                                    "sort": "asc"})
        return [_ticket(r) for r in rows]

    def get_ticket(self, number: int) -> Ticket:
        return _ticket(self._http.request("GET", f"{self._base}/issues/{number}"))

    def comments(self, number: int) -> list[Comment]:
        rows = self._pages(f"{self._base}/issues/{number}/notes", {"sort": "asc", "order_by": "created_at"})
        return [_comment(r) for r in rows if not r.get("system")]

    def post_comment(self, number: int, body: str) -> Comment:
        return _comment(self._http.request("POST", f"{self._base}/issues/{number}/notes", json={"body": body}))

    def add_label(self, number: int, label: str) -> None:
        self._http.request("PUT", f"{self._base}/issues/{number}", json={"add_labels": label})

    def remove_label(self, number: int, label: str) -> None:
        self._http.request("PUT", f"{self._base}/issues/{number}", json={"remove_labels": label})

    def _pages(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._http.request("GET", path, params={**params, "per_page": PAGE, "page": page})
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            page += 1


def _author(row: dict[str, Any]) -> Author:
    return Author(id=row["id"], username=row["username"])


def _ticket(row: dict[str, Any]) -> Ticket:
    return Ticket(number=row["iid"], title=row["title"], body=row.get("description") or "",
                  labels=frozenset(row.get("labels", [])))


def _comment(row: dict[str, Any]) -> Comment:
    return Comment(id=row["id"], author=_author(row["author"]), body=row["body"],
                   created_at=datetime.fromisoformat(row["created_at"]))
