"""HTTP client for GitLab's REST API with a token header (stdlib only)."""
from __future__ import annotations

import json as jsonlib
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from kargah.errors import TrackerError

ATTEMPTS = 3
RETRY_CODES = (500, 502, 503, 504)


class _Transient(TrackerError):
    """A failure worth another try (timeout, network, 5xx)."""


class UrllibHttp:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._base = base_url.rstrip("/") + "/api/v4/"
        self._token = token
        self._timeout = timeout
        self._sleep = sleep

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                json: dict[str, Any] | None = None) -> Any:
        """Reads are tried up to three times (GitLab sometimes times out); a write is never repeated."""
        attempts = ATTEMPTS if method == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                return self._once(method, path, params, json)
            except _Transient as exc:
                if attempt == attempts:
                    raise TrackerError(str(exc)) from exc.__cause__
                self._sleep(attempt)

    def _once(self, method: str, path: str, params: dict[str, Any] | None, json: dict[str, Any] | None) -> Any:
        url = self._base + path.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = jsonlib.dumps(json).encode() if json is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("PRIVATE-TOKEN", self._token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            # the message never includes the token: only method, path and GitLab's own reply
            message = f"{method} {path}: HTTP {exc.code} {exc.read()[:200].decode(errors='replace')}"
            raise (_Transient if exc.code in RETRY_CODES else TrackerError)(message) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise _Transient(f"{method} {path}: {exc}") from exc
        return jsonlib.loads(raw) if raw else None
