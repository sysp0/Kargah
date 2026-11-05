"""`dev web`: a read-only web viewer of the runs. Python's own HTTP server, the page in ui/, the TUI's View.

GET /                                     the page (ui/index.html, ui/app.js, ui/style.css)
GET /api/runs                             every run, newest first, and the poll interval of the page
GET /api/runs/<id>?since=<seq>            head, packages and usage of a run, and its live lines after <seq>
GET /api/runs/<id>/pkg/<pkg>              one package: findings, plan-problem note, the files of its run folder
GET /api/runs/<id>/pkg/<pkg>/file?path=   one of those files (only the end of a large one)

It never writes, never starts or stops a run, and stopping it (Ctrl+C) never touches a run.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import events as ev
from .config import Config
from .feature import code_hash
from .model import FINAL, Package, View, tree
from .usage import Usage

UI = Path(__file__).parent / "ui"
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}
LOCAL = {"127.0.0.1", "localhost", "::1"}


class NotFound(Exception):
    pass


def hostname(header: str) -> str:
    """The name part of a Host header: "localhost:8765" -> "localhost", "[::1]:8765" -> "::1"."""
    if header.startswith("["):
        return header[1:header.find("]")] if "]" in header else header
    return header.rsplit(":", 1)[0]


def usage_dict(u: Usage) -> dict:
    return {**asdict(u), "cache_pct": u.cache_pct}


def status(run: ev.Run, view: View) -> str:
    return view.outcome or ("running" if run.alive() else "stopped")


def package_row(p: Package) -> dict:
    return {"name": p.name, "state": p.state, "round": p.round, "started": p.started, "finished": p.finished,
            "step_started": p.step_started, "branch": p.branch, "commit": p.commit, "pr": p.pr, "note": p.note,
            "message": p.message, "last_result": p.last_result,
            "active": p.state not in FINAL and p.state != "waiting",
            "usage": {agent: usage_dict(u) for agent, u in p.usage.items()}}


def tree_rows(view: View) -> list[dict]:
    """The plan tree for the page: each Package becomes its row dict."""
    return [{**node, "pkg": package_row(node["pkg"]) if node.get("pkg") else None} for node in tree(view)]


class Runs:
    """One View per run, refreshed from its event log on each request; only the new bytes are read."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.views: dict[str, View] = {}
        self.lock = threading.Lock()

    def _view(self, run: ev.Run) -> View:
        view = self.views.setdefault(run.id, View(run_id=run.id))
        view.refresh(run.events_path)
        return view

    def _run(self, run_id: str) -> ev.Run:
        path = self.cfg.runs_dir / run_id
        if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith(".") \
                or not (path / "events.jsonl").is_file():
            raise NotFound(f"no run {run_id}")
        return ev.Run(path)

    def listing(self) -> dict:
        rows = []
        with self.lock:
            for run in reversed(ev.list_runs(self.cfg.runs_dir)):
                view = self._view(run)
                rows.append({"id": run.id, "kind": view.kind, "stage": view.stage, "started": view.started,
                             "finished": view.finished, "status": status(run, view),
                             "done": sum(1 for p in view.packages.values() if p.state == "done"),
                             "packages": len(view.order),
                             "claude_usd": view.totals.get("claude", Usage()).cost_usd})
        return {"poll_ms": int(self.cfg.get("web.poll_ms", 2000)), "now": time.time(), "runs": rows}

    def detail(self, run_id: str, since: int) -> dict:
        run = self._run(run_id)
        with self.lock:
            view = self._view(run)
            reset = since <= 0 or since > view.live_seq
            live = list(view.live) if reset else view.live_since(since)
            return {"id": run.id, "kind": view.kind, "stage": view.stage, "started": view.started,
                    "finished": view.finished, "last_ts": view.last_ts, "outcome": view.outcome,
                    "outcome_message": view.outcome_message,
                    "status": status(run, view), "current": view.current, "waiting_until": view.waiting_until,
                    "now": time.time(), "dir": str(run.dir),
                    "packages": [package_row(view.packages[name]) for name in view.order],
                    "tree": tree_rows(view), "gates": view.gates,
                    "totals": {agent: usage_dict(u) for agent, u in view.totals.items()},
                    "models": {key: usage_dict(u) for key, u in sorted(view.models.items())},
                    "live": [{"ts": ts, "pkg": pkg, "step": step, "text": str(text)} for ts, pkg, step, text in live],
                    "live_seq": view.live_seq, "live_reset": reset}

    def package(self, run_id: str, name: str) -> dict:
        run = self._run(run_id)
        with self.lock:
            view = self._view(run)
            if name not in view.packages:
                raise NotFound(f"no package {name} in run {run_id}")
            p = view.packages[name]
            findings = sorted(((r, text) for (pkg, r), text in view.findings.items() if pkg == name),
                              key=lambda item: -1 if item[0] is None else item[0])
        return {"name": name, "row": package_row(p), "note": self._note(p.note),
                "findings": [{"round": r, "text": text} for r, text in findings],
                "files": self._files(run, name)}

    def _note(self, rel: str | None) -> dict | None:
        """The text of a plan-problem note while it exists (a resume deletes it)."""
        if not rel:
            return None
        root = self.cfg.root.resolve()
        path = (root / rel).resolve()
        ok = path.is_relative_to(root) and path.suffix == ".md" and path.is_file()
        return {"path": rel, "text": path.read_text(encoding="utf-8", errors="replace")[:100_000] if ok else None}

    def _files(self, run: ev.Run, name: str) -> list[dict]:
        base = run.dir / name
        if not base.is_dir():
            return []
        found = [f for f in base.rglob("*") if f.is_file()]
        found.sort(key=lambda f: f.stat().st_mtime)
        return [{"path": f.relative_to(base).as_posix(), "size": f.stat().st_size, "mtime": f.stat().st_mtime}
                for f in found]

    def file(self, run_id: str, name: str, rel: str) -> dict:
        run = self._run(run_id)
        with self.lock:
            if name not in self._view(run).packages:
                raise NotFound(f"no package {name} in run {run_id}")
        base = (run.dir / name).resolve()
        path = (base / rel).resolve()
        if not rel or not path.is_relative_to(base) or not path.is_file():
            raise NotFound(f"no file {rel}")
        size = path.stat().st_size
        limit = int(self.cfg.get("web.file_tail_bytes", 300_000))
        with path.open("rb") as fh:
            if size > limit:
                fh.seek(size - limit)
            data = fh.read()
        return {"path": rel, "size": size, "truncated": size > limit, "text": data.decode("utf-8", "replace")}


class Handler(BaseHTTPRequestHandler):
    runs: Runs                     # set by make_server
    hosts: set[str] | None = None  # Host names a local viewer answers; a page on another site cannot rebind to it

    def log_message(self, format, *args) -> None:   # the page polls every few seconds; keep the terminal quiet
        return

    def send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code: int = 200) -> None:
        self.send(code, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"),
                  "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.hosts is not None and hostname(self.headers.get("Host") or "") not in self.hosts:
            self.send_json({"error": "open this viewer as localhost or 127.0.0.1"}, 403)
            return
        url = urlparse(self.path)
        if url.path in STATIC:
            path = UI / STATIC[url.path]
            self.send(200, path.read_bytes(), TYPES[path.suffix])
            return
        parts = [unquote(part) for part in url.path.strip("/").split("/")]
        query = parse_qs(url.query)
        try:
            if parts[:2] != ["api", "runs"]:
                raise NotFound(url.path)
            if len(parts) == 2:
                self.send_json(self.runs.listing())
            elif len(parts) == 3:
                since = query.get("since", ["0"])[0]
                self.send_json(self.runs.detail(parts[2], int(since) if since.isdigit() else 0))
            elif len(parts) == 5 and parts[3] == "pkg":
                self.send_json(self.runs.package(parts[2], parts[4]))
            elif len(parts) == 6 and parts[3] == "pkg" and parts[5] == "file":
                self.send_json(self.runs.file(parts[2], parts[4], query.get("path", [""])[0]))
            else:
                raise NotFound(url.path)
        except NotFound as exc:
            self.send_json({"error": str(exc)}, 404)


class Server(ThreadingHTTPServer):
    """Stops when devchain's code changes on disk (a pull), so serve() restarts with the new code: the page is read
    from disk on every request, the Python that draws its data only at start."""
    daemon_threads = True
    allow_reuse_address = True
    reload = False

    def service_actions(self) -> None:
        now = time.monotonic()
        if now - getattr(self, "checked", 0) < 2:
            return
        self.checked = now
        if code_hash(self.root) != self.code:
            self.reload = True
            threading.Thread(target=self.shutdown, daemon=True).start()


def make_server(cfg: Config, host: str, port: int) -> Server:
    handler = type("RunsHandler", (Handler,), {"runs": Runs(cfg), "hosts": LOCAL if host in LOCAL else None})
    server = Server((host, port), handler)
    server.root, server.code = cfg.root, code_hash(cfg.root)
    return server


def serve(cfg: Config, host: str | None = None, port: int | None = None) -> int:
    host = host or str(cfg.get("web.host", "127.0.0.1"))
    port = int(cfg.get("web.port", 8765) if port is None else port)
    server = make_server(cfg, host, port)
    print(f"devchain: web viewer on http://{host}:{server.server_address[1]}/ "
          "(read-only; Ctrl+C stops the viewer, never a run)")
    if host not in LOCAL:
        print("devchain: open to the network: anyone who reaches this port can read the logs and prompts")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    if server.reload:
        print("devchain: devchain changed on disk; the web viewer restarts with the new code", flush=True)
        os.execv(sys.executable, [sys.executable, "-m", "devchain", *sys.argv[1:]])
    return 0
