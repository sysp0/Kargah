"""A small read-only web server for the local UI: GET only, bound to the machine it runs on."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from kargah.errors import KargahError
from kargah.orchestrator import uidata

PAGE = Path(__file__).resolve().parent.parent / "defaults" / "ui" / "index.html"


def make_server(workdir: Path, host: str, port: int, inbox: Callable[[], list[dict[str, Any]]] | None,
                issue_base: str) -> ThreadingHTTPServer:
    routes: dict[str, Callable[[dict[str, list[str]]], Any]] = {
        "/api/dashboard": lambda q: uidata.dashboard(workdir, q.get("since", ["7d"])[0], datetime.now(UTC)),
        "/api/runs": lambda q: uidata.runs(workdir),
        "/api/scorers": lambda q: uidata.scorers(workdir),
        "/api/improvements": lambda q: uidata.improvements(workdir),
        "/api/benchmarks": lambda q: uidata.benchmarks(workdir),
        "/api/inbox": lambda q: {"rows": inbox() if inbox else [], "available": inbox is not None},
        "/api/config": lambda q: {"issue_base": issue_base},
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the name http.server looks for
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif url.path in routes:
                try:
                    self._send(200, "application/json", json.dumps(routes[url.path](parse_qs(url.query))).encode())
                except KargahError as exc:
                    self._send(400, "application/json", json.dumps({"error": str(exc)}).encode())
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self) -> None:  # noqa: N802
            self._send(405, "text/plain", b"read-only")

        do_PUT = do_DELETE = do_PATCH = do_POST  # noqa: N815

        def _send(self, status: int, kind: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - quiet
            pass

    return ThreadingHTTPServer((host, port), Handler)
