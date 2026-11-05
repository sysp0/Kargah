"""`dev watch`: a Textual viewer of one run. It only reads the event log; quitting never stops the run."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, RichLog, Static

from . import events as ev
from .model import FINAL, View, duration, tree
from .plain import usage_table
from .usage import Usage, short

STATE_STYLE = {
    "done": "bold green", "failed": "bold red", "blocked": "bold yellow", "app_bug": "bold magenta",
    "heavy": "bold red", "needs_decision": "bold yellow",
    "waiting": "dim", "codex": "cyan", "review": "blue", "accept": "yellow", "tests": "yellow",
    "build_ui": "yellow", "ui_design": "magenta", "commit": "green", "resume": "cyan", "triage": "magenta",
    "playwright": "yellow",
    "gate": "bold yellow", "approved": "bold green", "skipped": "yellow", "waiting for test": "bold yellow",
    "QA running": "yellow", "building": "cyan", "not started": "dim", "fixed": "green", "fixing": "cyan",
    "closed": "dim green", "question": "magenta", "needs-info": "magenta", "decide": "bold red",
}
PART_ICON = {"done": "✔", "approved": "✔", "skipped": "⏭", "waiting for test": "⏸", "QA running": "⏸",
             "building": "⚙", "not started": "○"}
STEP_STYLE = {"codex": "cyan", "review": "blue", "triage": "magenta", "accept": "yellow", "tests": "yellow",
              "state": "bold", "findings": "red", "limit": "bold yellow", "note": "dim"}


class TextScreen(ModalScreen):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "close")]
    DEFAULT_CSS = """
    TextScreen { align: center middle; }
    TextScreen > VerticalScroll { width: 90%; height: 85%; border: round $accent; background: $surface; padding: 0 1; }
    """

    def __init__(self, title: str, body: str):
        super().__init__()
        self.title_text, self.body = title, body

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(Text(self.title_text, style="bold"))
            yield Static(Text(self.body or "(empty)"))


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("y", "answer(True)", "yes"), Binding("n,escape,q", "answer(False)", "no")]
    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Static { width: 70; height: auto; border: round $warning; background: $surface; padding: 1 2; }
    """

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        body = Text(self.question + "\n\n", style="bold")
        body.append("y", style="bold green")
        body.append(" yes    ")
        body.append("n", style="bold red")
        body.append(" no")
        yield Static(body)

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)


def usage_panel(view: View) -> Text:
    out = Text()
    for agent, label in (("codex", "Codex"), ("claude", "Claude")):
        u: Usage = view.totals.get(agent, Usage())
        pct = u.cache_pct
        out.append(f"{label:<7}", style="bold")
        out.append(f"{u.calls} calls   in {short(u.input)}   ")
        out.append(f"cached {short(u.cached)} " + (f"({pct:.0f}%)" if pct is not None else "(-)"), style="green")
        out.append("\n" + " " * 7)
        if u.cache_write:
            out.append(f"write {short(u.cache_write)}   ")
        out.append(f"out {short(u.output)}")
        if u.reasoning:
            out.append(f"   reasoning {short(u.reasoning)}")
        if agent == "claude":
            out.append("\n" + " " * 7)
            out.append(f"cost ${u.cost_usd:.2f}", style="bold yellow")
            if u.calls:
                out.append(f"   avg ${u.cost_usd / u.calls:.2f} per call")
        out.append("\n")
    if view.waiting_until and not view.finished:
        out.append(f"Usage limit: waiting {duration(view.waiting_until - time.time())}", style="bold yellow")
    else:
        out.append("Usage limit: no wait", style="dim")
    return out


class WatchApp(App):
    TITLE = "devchain"
    CSS = """
    #head { height: 1; background: $boost; padding: 0 1; }
    #top { height: 16; }
    #pkgs { width: 3fr; height: 100%; border: round $primary; }
    #usage { width: 2fr; height: 100%; border: round $primary; padding: 0 1; overflow-y: auto; }
    #live { border: round $secondary; height: 1fr; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    """
    BINDINGS = [
        Binding("q", "quit", "quit (run continues)"),
        Binding("v", "verdict", "verdict"),
        Binding("f", "findings", "findings"),
        Binding("d", "diff", "diff --stat"),
        Binding("l", "log", "last log"),
        Binding("u", "usage", "usage table"),
        Binding("r", "resume", "resume"),
        Binding("s", "stop", "stop run"),
    ]

    def __init__(self, run: ev.Run, root: Path):
        super().__init__()
        self.run_ref, self.root = run, root
        self.view = View(run_id=run.id)
        self.seen = 0

    def compose(self) -> ComposeResult:
        yield Static(id="head")
        with Horizontal(id="top"):
            table = DataTable(id="pkgs", cursor_type="row", zebra_stripes=True)
            yield table
            yield Static(id="usage")
        yield RichLog(id="live", wrap=True, markup=False, highlight=False, max_lines=2000)
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#pkgs", DataTable)
        table.border_title = "Packages"
        table.add_columns("Pkg", "State", "Round", "Time", "Last step", "Detail")
        self.query_one("#usage", Static).border_title = "Usage"
        self.query_one("#live", RichLog).border_title = "Live"
        self.tick()
        self.set_interval(0.5, self.tick)

    # ---- refresh ------------------------------------------------------------------------------------------------
    def tick(self) -> None:
        self.view.refresh(self.run_ref.events_path)
        v = self.view
        now = time.time()
        end = v.finished or now
        head = Text()
        head.append(f"run {v.run_id}", style="bold")
        head.append(f"   {v.kind} {v.stage}")
        if v.current and v.current in v.packages and v.packages[v.current].branch:
            head.append(f"   branch {v.packages[v.current].branch}")
        done = sum(1 for p in v.packages.values() if p.state == "done")
        head.append(f"   {done}/{len(v.order)} done   elapsed {duration(end - (v.started or end))}")
        if v.outcome:
            head.append(f"   {v.outcome.upper()}", style=STATE_STYLE.get(v.outcome, "bold"))
        elif not self.run_ref.alive():
            head.append("   NOT RUNNING", style="bold red")
        self.query_one("#head", Static).update(head)
        self.query_one("#usage", Static).update(usage_panel(v))
        self.fill_table(now)
        log = self.query_one("#live", RichLog)
        for ts, pkg, step, text in v.live_since(self.seen):
            line = Text(datetime.fromtimestamp(ts).strftime("%H:%M:%S "), style="dim")
            line.append(f"{pkg or '-':<6} ", style="bold")
            line.append(f"{step:<9} ", style=STEP_STYLE.get(step, ""))
            line.append(str(text))
            log.write(line)
        self.seen = v.live_seq
        self.query_one("#status", Static).update(Text(v.outcome_message or str(self.run_ref.dir), style="dim"))

    def tree_rows(self, now: float) -> list:
        rows = []
        for node in tree(self.view):
            p = node.get("pkg")
            indent = "  " * node["depth"]
            if node["kind"] in ("part", "group"):
                state = node["state"]
                label = Text(f"{PART_ICON.get(state, '▾')} {node['label']}", style="bold")
                cells = [label, Text(state, style=STATE_STYLE.get(state, "bold")), "", node["detail"],
                         node["counts"], Text(node["title"][:48], style="dim")]
            elif node["kind"] == "issue":
                state = node["issue"].get("status", "")
                cells = [Text(f"{indent}{node['icon']} {node['label']}"), Text(node["state"], style=STATE_STYLE.get(
                    state, "")), "" if not p or p.round is None else str(p.round),
                         duration(p.elapsed(now)) if p else "", node["detail"], Text(node["title"][:48], style="dim")]
            else:
                style = STATE_STYLE.get(p.state, "bold cyan")
                marker = "▶ " if p.state not in FINAL and p.state != "waiting" else ""
                detail = f"{node['title']}  {p.commit or ''}".strip()
                cells = [Text(f"{indent}{node['label']}", style="bold"), Text(marker + p.state, style=style),
                         "" if p.round is None else str(p.round), duration(p.elapsed(now)) if p.started else "",
                         p.last_result or node["counts"], Text(detail[:48], style="dim")]
            rows.append((node["key"], cells))
        return rows

    def fill_table(self, now: float) -> None:
        """Rows in place while the package list is the same, so the scroll position and cursor stay."""
        table = self.query_one("#pkgs", DataTable)
        rows = self.tree_rows(now)
        for name in [] if rows else self.view.order:
            p = self.view.packages[name]
            style = STATE_STYLE.get(p.state, "bold cyan")
            marker = "▶ " if p.state not in FINAL and p.state != "waiting" else ""
            detail = f"{p.commit}  PR: {p.pr.rsplit('/pull/new/', 1)[-1]}" if p.pr else (p.commit or p.message or "")
            rows.append((name, [Text(name, style="bold"), Text(marker + p.state, style=style),
                                "" if p.round is None else str(p.round), duration(p.elapsed(now)),
                                p.last_result, Text(detail[:48], style="dim")]))
        if [key.value for key in table.rows] == [name for name, _ in rows]:
            for i, (_, cells) in enumerate(rows):
                for j, cell in enumerate(cells):
                    table.update_cell_at(Coordinate(i, j), cell)
            return
        keep = table.cursor_row
        table.clear()
        for name, cells in rows:
            table.add_row(*cells, key=name)
        if rows:
            table.move_cursor(row=min(keep, len(rows) - 1))

    # ---- actions ------------------------------------------------------------------------------------------------
    def selected(self) -> str | None:
        """The run folder name of the selected row: a package, or the row an issue was built as."""
        table = self.query_one("#pkgs", DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(Coordinate(min(table.cursor_row, table.row_count - 1), 0)).row_key.value
        if key and key.startswith("issue:"):
            node = next((n for n in tree(self.view) if n["key"] == key), None)
            return node["issue"].get("row") if node else None
        return None if not key or key.startswith(("part:", "group:")) else key

    def latest(self, pattern: str) -> Path | None:
        name = self.selected()
        if not name:
            return None
        files = sorted((self.run_ref.dir / name).glob(pattern), key=lambda p: p.stat().st_mtime)
        return files[-1] if files else None

    def show_file(self, title: str, pattern: str) -> None:
        path = self.latest(pattern)
        body = path.read_text(encoding="utf-8", errors="replace")[-20000:] if path else "nothing yet"
        self.push_screen(TextScreen(f"{title}: {path or '-'}", body))

    def action_verdict(self) -> None:
        self.show_file("Verdict", "verdict-*.md")

    def action_findings(self) -> None:
        self.show_file("Findings", "findings-*.md")

    def action_log(self) -> None:
        name = self.selected()
        files = sorted((self.run_ref.dir / name).rglob("*.log"), key=lambda p: p.stat().st_mtime) if name else []
        path = files[-1] if files else None
        body = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]) if path else "no log"
        self.push_screen(TextScreen(f"Log: {path or '-'}", body))

    def action_diff(self) -> None:
        out = subprocess.run(["git", "diff", "--stat", "HEAD"], cwd=self.root, capture_output=True, text=True)
        untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=self.root,
                                   capture_output=True, text=True).stdout.strip()
        body = (out.stdout or "no tracked changes") + (f"\n\nuntracked:\n{untracked}" if untracked else "")
        self.push_screen(TextScreen("Working tree", body))

    def action_usage(self) -> None:
        self.push_screen(TextScreen("Usage per package", usage_table(self.view)))


    def action_resume(self) -> None:
        if self.run_ref.alive():
            if self.view.kind == "loop":   # a waiting loop reads the issues again at once
                try:
                    os.kill(self.run_ref.pid(), signal.SIGUSR1)
                except (OSError, TypeError) as exc:
                    self.notify(f"Wake failed: {exc}", severity="error")
                    return
                self.notify("Woke the loop: it reads the issues now.")
                return
            self.notify("The run is still running.", severity="warning")
            return
        if self.view.outcome == "done":
            self.notify("Nothing left to resume: the run is done.", severity="warning")
            return
        state = self.view.outcome or "not running"
        self.push_screen(ConfirmScreen(f"Resume run {self.run_ref.id} ({state})?\n"
                                       "It keeps the work in the tree and continues in the background."),
                         self.resume_answered)

    def resume_answered(self, yes: bool | None) -> None:
        if not yes:
            return
        from .cli import launch, resume_session

        try:
            argv = ["run", self.view.stage, "--run-id", self.run_ref.id] if self.view.kind == "loop" \
                else ["resume", self.run_ref.id]
            where = launch(self.root, self.run_ref, argv, resume_session(self.run_ref))
        except Exception as exc:  # tmux missing a session name, a failed spawn: say it, keep the viewer
            self.notify(f"Resume failed: {exc}", severity="error")
            return
        self.notify(f"Resumed in {where}.")


    def action_stop(self) -> None:
        if not self.run_ref.alive():
            self.notify("The run is not running.", severity="warning")
            return
        self.push_screen(ConfirmScreen(f"Stop run {self.run_ref.id}?\n"
                                       "Codex and the review stop now; the work stays in the tree for resume."),
                         self.stop_answered)

    def stop_answered(self, yes: bool | None) -> None:
        if not yes:
            return
        try:
            self.run_ref.stop()
        except (OSError, ValueError) as exc:
            self.notify(f"Stop failed: {exc}", severity="error")
            return
        self.notify("Stopping the run; press r to resume it later.")


def run_tui(run: ev.Run, root: Path) -> None:
    WatchApp(run, root).run()
