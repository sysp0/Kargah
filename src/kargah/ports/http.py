"""A JSON-over-HTTP client, so adapters can be tested without a network."""
from __future__ import annotations

from typing import Any, Protocol


class HttpClient(Protocol):
    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                json: dict[str, Any] | None = None) -> Any:
        """Return the decoded JSON body; raise TrackerError on a failed call."""
