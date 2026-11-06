"""Read every page of a GitLab list endpoint."""
from __future__ import annotations

from typing import Any

from kargah.ports.http import HttpClient

PAGE = 100


def pages(http: HttpClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = http.request("GET", path, params={**params, "per_page": PAGE, "page": page})
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        page += 1
