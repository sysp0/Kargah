"""HTTP client for GitLab's REST API with a token header (stdlib only)."""
from __future__ import annotations

import json as jsonlib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from kargah.errors import TrackerError


class UrllibHttp:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/") + "/api/v4/"
        self._token = token
        self._timeout = timeout

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                json: dict[str, Any] | None = None) -> Any:
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
            raise TrackerError(f"{method} {path}: HTTP {exc.code} {exc.read()[:200].decode(errors='replace')}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TrackerError(f"{method} {path}: {exc}") from exc
        return jsonlib.loads(raw) if raw else None
