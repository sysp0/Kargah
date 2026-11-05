import json
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

from helpers import setup

from kargah import cli, config, events, web

PASS = {"verdict": "VERDICT: PASS\nCOMMIT: Add package one"}
WORK = {"write": {"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    assert True\n"}}
NOTE = "docs/devchain-plan/x/blocked-P1.md"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never through a proxy of the test machine


@pytest.fixture
def viewer(repo):
    """Start `dev web` on a free port of this repo; yields a function that GETs a path."""
    servers = []

    def start():
        server = web.make_server(config.load(repo.root), "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        port = server.server_address[1]

        def get(path, host=None):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": host} if host else {})
            try:
                with OPENER.open(request, timeout=5) as res:
                    return res.status, res.headers.get("Content-Type"), res.read()
            except urllib.error.HTTPError as err:
                return err.code, err.headers.get("Content-Type"), err.read()

        return get

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def data(response):
    code, _, body = response
    return code, json.loads(body)


def test_web_serves_the_page_and_lists_the_runs(repo, viewer):
    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    assert cli.main(["run", "x", "--once"]) == 0
    get = viewer()
    code, kind, body = get("/")
    assert code == 200 and kind.startswith("text/html") and b"devchain" in body
    assert get("/app.js")[1].startswith("text/javascript") and get("/style.css")[1].startswith("text/css")
    code, listing = data(get("/api/runs"))
    assert code == 200 and listing["poll_ms"] == 2000
    [row] = listing["runs"]
    assert row["status"] == "stopped" and row["done"] == 1 and row["packages"] == 1 and row["claude_usd"] == 0.25


def test_run_detail_sends_only_the_live_lines_after_since(repo, viewer):
    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    cli.main(["run", "x", "--once"])
    run = events.open_run(repo.root / ".devchain/runs", None)
    get = viewer()
    code, d = data(get(f"/api/runs/{run.id}?since=0"))
    assert code == 200 and d["live_reset"] and d["status"] == "stopped"
    [p1] = d["packages"]
    assert p1["name"] == "P1" and p1["state"] == "done" and p1["usage"]["claude"]["cost_usd"] == 0.25
    assert d["models"]["claude fake-review"]["calls"] == 1 and d["live"]
    seq = d["live_seq"]
    assert data(get(f"/api/runs/{run.id}?since={seq}"))[1]["live"] == []
    run.emit("note", pkg="P1", text="a new line")
    later = data(get(f"/api/runs/{run.id}?since={seq}"))[1]
    assert [line["text"] for line in later["live"]] == ["a new line"] and not later["live_reset"]


def add_plan_folder(repo):
    folder = repo.root / "docs/devchain-plan/2026-10-19-demo"
    folder.mkdir(parents=True)
    (folder / "01-first.md").write_text("| Pn | Title | files | acceptance |\n|---|---|---|---|\n"
                                        "| P1 | One | `src/a.py` | test |\n")
    for args in (("add", "-A"), ("commit", "-q", "-m", "plan"), ("push", "-q", "origin", "main")):
        subprocess.run(["git", *args], cwd=repo.root, check=True, capture_output=True)


def test_package_detail_shows_the_plan_note_files_and_findings(repo, viewer):
    setup(repo)
    repo.codex({"write": {NOTE: "1) row P1 misses a caller\n"}, "blocked": f"plan problem, see {NOTE}"})
    assert cli.main(["run", "x", "--once"]) == 0
    run = events.open_run(repo.root / ".devchain/runs", None)
    run.emit("findings", pkg="P1", round=0, text="1. src/a.py:1 - missing guard")
    get = viewer()
    code, d = data(get(f"/api/runs/{run.id}/pkg/P1"))
    assert code == 200 and d["row"]["state"] == "blocked"
    assert d["note"] is None   # the loop keeps the stopped work aside, so the note leaves the tree
    assert d["findings"] == [{"round": 0, "text": "1. src/a.py:1 - missing guard"}]
    paths = [f["path"] for f in d["files"]]
    assert "prompt-0.txt" in paths and "codex-0/codex-1.log" in paths
    code, f = data(get(f"/api/runs/{run.id}/pkg/P1/file?path=prompt-0.txt"))
    assert code == 200 and "package P1" in f["text"] and not f["truncated"]


def test_the_viewer_reads_nothing_outside_the_run_folder(repo, viewer):
    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    cli.main(["run", "x", "--once"])
    run = events.open_run(repo.root / ".devchain/runs", None)
    get = viewer()
    assert get(f"/api/runs/{run.id}/pkg/P1/file?path=../../../devchain.toml")[0] == 404
    assert get(f"/api/runs/{run.id}/pkg/P1/file?path=/etc/passwd")[0] == 404
    assert get(f"/api/runs/{run.id}/pkg/P9")[0] == 404
    assert get("/api/runs/..%2F..")[0] == 404 and get("/api/runs/nope")[0] == 404
    assert get("/api/nothing")[0] == 404 and get("/devchain.toml")[0] == 404
    # a page of another site that rebinds its name to 127.0.0.1 is refused; localhost and the IP are fine
    assert get("/api/runs", host="evil.example:8765")[0] == 403
    assert get("/api/runs", host="localhost:8765")[0] == 200 and get("/", host="[::1]:8765")[0] == 200


def test_a_large_file_shows_only_its_end(repo, viewer):
    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    cli.main(["run", "x", "--once"])
    run = events.open_run(repo.root / ".devchain/runs", None)
    (run.dir / "P1" / "big.log").write_text("x" * 50 + "THE END")
    with (repo.root / "devchain.toml").open("a") as fh:
        fh.write("\n[web]\nfile_tail_bytes = 10\n")
    get = viewer()
    code, f = data(get(f"/api/runs/{run.id}/pkg/P1/file?path=big.log"))
    assert code == 200 and f["truncated"] and f["size"] == 57 and f["text"] == "xxxTHE END"


def test_dev_web_passes_host_and_port(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(web, "serve", lambda cfg, host, port: calls.append((host, port)) or 0)
    assert cli.main(["web"]) == 0 and cli.main(["web", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert calls == [(None, None), ("0.0.0.0", 9000)]


def test_hostname():
    assert web.hostname("localhost:8765") == "localhost" and web.hostname("127.0.0.1") == "127.0.0.1"
    assert web.hostname("[::1]:8765") == "::1" and web.hostname("[::1]") == "::1"


def test_the_viewer_stops_to_reload_when_devchain_changes_on_disk(repo):
    server = web.make_server(config.load(repo.root), "127.0.0.1", 0)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    (repo.root / "devchain.toml").write_text((repo.root / "devchain.toml").read_text() + "\n# pulled\n")
    thread.join(timeout=5)
    server.server_close()
    assert not thread.is_alive() and server.reload   # serve() then execs itself with the new code
