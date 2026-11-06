"""Merge requests on GitLab."""
from __future__ import annotations

from urllib.parse import quote

from kargah.errors import TrackerError
from kargah.ports.http import HttpClient

DRAFT = "Draft: "


class GitLabHost:
    def __init__(self, http: HttpClient, project: str, web_url: str) -> None:
        self._http = http
        self._base = f"projects/{quote(project, safe='')}/merge_requests"
        self._web = web_url

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

    def _find(self, branch: str) -> dict | None:
        rows = self._http.request("GET", self._base, params={"source_branch": branch, "state": "opened"})
        return rows[0] if rows else None
