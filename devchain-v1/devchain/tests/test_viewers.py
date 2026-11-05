import asyncio

import pytest

from helpers import setup

from devchain import cli, events, plain
from devchain.model import load

PASS = {"verdict": "VERDICT: PASS\nCOMMIT: Add package one"}
WORK = {"write": {"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    assert True\n"}}


def test_plain_summary_and_usage_table(repo, capsys):
    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    assert cli.main(["run", "x", "--once"]) == 0
    run = events.open_run(repo.root / ".devchain/runs", None)
    text = plain.summary(load(run))
    assert "✓ P1" in text and "stopped" in text and "$0.25" in text and "80%)" in text and "69%)" in text
    assert "[P1]" in plain.usage_table(load(run))
    assert cli.main(["runs"]) == 0
    assert "stopped" in capsys.readouterr().out
    assert cli.main(["watch", "--plain"]) == 0


def test_tui_renders_packages_usage_and_live_log(repo):
    textual = pytest.importorskip("textual")
    assert textual
    from devchain.tui import WatchApp

    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    assert cli.main(["run", "x", "--once"]) == 0
    run = events.open_run(repo.root / ".devchain/runs", None)

    async def scenario():
        app = WatchApp(run, repo.root)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#pkgs")
            rows = [" ".join(str(c) for c in table.get_row_at(i)) for i in range(table.row_count)]
            assert any("P1" in r and "done" in r for r in rows)
            assert "$0.25" in str(app.query_one("#usage").render())
            await pilot.press("u")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "TextScreen"
            await pilot.press("escape")

    asyncio.run(scenario())


def test_tui_package_table_has_fixed_height_and_keeps_its_scroll(tmp_path):
    pytest.importorskip("textual")
    from devchain.tui import WatchApp

    run = events.create(tmp_path / "runs", "qa")
    names = [f"S{i}" for i in range(1, 31)]
    run.emit("run_started", kind="qa", stage="suite", packages=names)
    run.emit("pkg", pkg="S1", state="writing", round=0)

    async def scenario():
        app = WatchApp(run, tmp_path)
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            table = app.query_one("#pkgs")
            assert table.row_count == 30
            assert table.size.height < 20
            await pilot.click("#pkgs")
            for _ in range(25):
                await pilot.press("down")
            await pilot.pause()
            row, y = table.cursor_row, table.scroll_y
            assert y > 0
            run.emit("pkg", pkg="S2", state="playwright", round=0)
            app.tick()
            await pilot.pause()
            assert (table.cursor_row, table.scroll_y) == (row, y)
            assert "playwright" in str(table.get_row_at(1)[1])

    asyncio.run(scenario())


def test_tui_resume_asks_first_then_launches_the_run(repo, monkeypatch):
    pytest.importorskip("textual")
    from devchain.tui import WatchApp

    launched = []
    monkeypatch.setattr(cli, "launch", lambda root, run, argv, session: launched.append(argv) or "tmux x")
    repo.codex(WORK)
    repo.claude({"exit": 1})
    setup(repo)
    assert cli.main(["run", "x", "--once"]) == 0
    run = events.open_run(repo.root / ".devchain/runs", None)
    (run.dir / "pid").write_text("999999999")  # the run ended; its pid was this test process

    async def scenario():
        app = WatchApp(run, repo.root)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "ConfirmScreen"
            await pilot.press("n")
            await pilot.pause()
            assert launched == []
            await pilot.press("r")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert launched == [["run", "x", "--run-id", run.id]]

    asyncio.run(scenario())
    run.emit("run_resumed")
    view = load(run)
    assert view.outcome == "" and view.finished is None


def test_tui_stop_asks_first_then_stops_the_run(repo, monkeypatch):
    pytest.importorskip("textual")
    from devchain.tui import WatchApp

    stopped = []
    monkeypatch.setattr(events.Run, "stop", lambda self: stopped.append(self.id))
    repo.codex(WORK)
    repo.claude(PASS)
    setup(repo)
    assert cli.main(["run", "x", "--once"]) == 0
    run = events.open_run(repo.root / ".devchain/runs", None)  # its pid is this test process: alive

    async def scenario():
        app = WatchApp(run, repo.root)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "ConfirmScreen"
            await pilot.press("n")
            await pilot.pause()
            assert stopped == []
            await pilot.press("s")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert stopped == [run.id]

    asyncio.run(scenario())
