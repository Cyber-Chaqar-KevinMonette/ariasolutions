"""data_science_screen.py — the Data Science workspace.

Create custom windows with metrics, data tables, buttons, text,
and diff views. Green for additions, red for removals, nothing
cut short.

Esc / q / Close to dismiss.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class DataScienceScreen(ModalScreen):
    """◊ Data Science — custom windows with metrics, data, buttons, text."""

    BINDINGS = [Binding("escape,q", "close_data_science", "close")]

    def action_close_data_science(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        event.stop()
        if event.button.id == "ds-close":
            self.app.pop_screen()
            return
        if event.button.id and event.button.id.startswith("ds-action-"):
            action = event.button.id[len("ds-action-"):]
            self._run_ds_action(action)

    def _run_ds_action(self, action: str) -> None:
        try:
            if action == "refresh-metrics":
                self._refresh_metrics()
            elif action == "add-window":
                self._add_window()
            elif action == "add-table":
                self._add_table()
            elif action == "add-text":
                self._add_text()
            elif action == "add-button":
                self._add_button()
            elif action == "add-diff":
                self._add_diff()
        except Exception as exc:  # noqa: BLE001
            self._show_status(f"[red]error: {exc!r}[/red]")

    def _refresh_metrics(self) -> None:
        try:
            metrics_text = self._collect_metrics()
            widget = self.query_one("#ds-metrics", Static)
            widget.update(metrics_text)
        except Exception:  # noqa: BLE001
            pass

    def _collect_metrics(self) -> str:
        lines = ["[b]System Metrics[/b]"]
        try:
            import os
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu = psutil.cpu_percent(interval=0)
            lines.append(f"CPU: [cyan]{cpu}%[/cyan]")
            lines.append(f"Memory: [cyan]{mem.percent}%[/cyan] ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)")
            lines.append(f"Disk: [cyan]{disk.percent}%[/cyan] ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)")
        except Exception:
            lines.append("[dim]metrics unavailable[/dim]")
        try:
            from sovereign_agent.loop import _token_stats
            lines.append(f"Tokens: [cyan]{_token_stats.get('tokens_used', 0):,}[/cyan]")
            lines.append(f"Iter: [cyan]{_token_stats.get('iterations', 0)}[/cyan]")
            lines.append(f"Tok/s: [cyan]{_token_stats.get('tok_s', 0.0):.1f}[/cyan]")
        except Exception:
            pass
        return "\n".join(lines)

    def _add_window(self) -> None:
        scroll = self.query_one("#ds-scroll", VerticalScroll)
        idx = len(scroll.children) + 1
        with Vertical(id=f"ds-window-{idx}", classes="ds-window"):
            yield Static(f"[b]Window {idx}[/b]  [dim](empty — add widgets below)[/dim]", classes="ds-window-title")
            yield Static("", id=f"ds-content-{idx}", classes="ds-content")
        self._show_status(f"[green]added window {idx}[/green]")

    def _add_table(self) -> None:
        scroll = self.query_one("#ds-scroll", VerticalScroll)
        idx = len(scroll.children) + 1
        table_lines = [
            "[b]Sample Data Table[/b]",
            "[dim]col_a    col_b    col_c[/dim]",
            "[green]1.0      2.0      3.0[/green]",
            "[red]4.0      5.0      6.0[/red]",
            "[green]7.0      8.0      9.0[/green]",
        ]
        with Vertical(id=f"ds-window-{idx}", classes="ds-window"):
            yield Static(f"[b]Table {idx}[/b]", classes="ds-window-title")
            yield Static("\n".join(table_lines), classes="ds-content")
        self._show_status(f"[green]added table {idx}[/green]")

    def _add_text(self) -> None:
        scroll = self.query_one("#ds-scroll", VerticalScroll)
        idx = len(scroll.children) + 1
        with Vertical(id=f"ds-window-{idx}", classes="ds-window"):
            yield Static(f"[b]Text {idx}[/b]", classes="ds-window-title")
            yield Static("[dim]paste your markdown or plain text here...[/dim]", classes="ds-content")
        self._show_status(f"[green]added text {idx}[/green]")

    def _add_button(self) -> None:
        scroll = self.query_one("#ds-scroll", VerticalScroll)
        idx = len(scroll.children) + 1
        with Vertical(id=f"ds-window-{idx}", classes="ds-window"):
            yield Static(f"[b]Button {idx}[/b]", classes="ds-window-title")
            yield Button("click me", id=f"ds-action-btn-{idx}", variant="primary")
            yield Static("[dim]buttons trigger actions in the data science workspace[/dim]", classes="ds-content")
        self._show_status(f"[green]added button {idx}[/green]")

    def _add_diff(self) -> None:
        scroll = self.query_one("#ds-scroll", VerticalScroll)
        idx = len(scroll.children) + 1
        from sovereign_agent.cockpit.run_surface import _diff_render
        old_text = "line one\nline two\nline three"
        new_text = "line one\nline two modified\nline three\nline four added"
        diff_lines = _diff_render(old_text, new_text)
        with Vertical(id=f"ds-window-{idx}", classes="ds-window"):
            yield Static(f"[b]Diff {idx}[/b]", classes="ds-window-title")
            yield Static("\n".join(diff_lines), classes="ds-content")
        self._show_status(f"[green]added diff {idx}[/green]")

    def _show_status(self, msg: str) -> None:
        try:
            status = self.query_one("#ds-status", Static)
            status.update(msg)
        except Exception:  # noqa: BLE001
            pass

    def compose(self) -> ComposeResult:
        with Vertical(id="ds-modal"):
            with Horizontal(id="ds-toolbar"):
                yield Button("+ window", id="ds-action-add-window", variant="primary")
                yield Button("+ table", id="ds-action-add-table")
                yield Button("+ text", id="ds-action-add-text")
                yield Button("+ button", id="ds-action-add-button")
                yield Button("+ diff", id="ds-action-add-diff")
                yield Button("↻ refresh", id="ds-action-refresh-metrics")
                yield Button("✕ Close", id="ds-close", variant="error")
            yield Static("", id="ds-status", classes="ds-status")
            with VerticalScroll(id="ds-scroll"):
                yield Static("[b]Data Science Workspace[/b]  [dim]create windows, add metrics, data, buttons, and text[/dim]", classes="ds-welcome")
                with Vertical(id="ds-window-1", classes="ds-window"):
                    yield Static("[b]Metrics[/b]", classes="ds-window-title")
                    yield Static(self._collect_metrics(), id="ds-metrics", classes="ds-content")

    DEFAULT_CSS = """
    DataScienceScreen {
        align: center middle;
        background: $surface 60%;
    }
    #ds-modal {
        width: 80;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #ds-toolbar {
        height: 1;
        padding: 0 0 1 0;
    }
    #ds-toolbar Button {
        margin: 0 1 0 0;
    }
    #ds-scroll {
        height: auto;
        max-height: 70%;
    }
    .ds-window {
        padding: 1;
        margin: 1 0;
        border: solid $primary 30%;
        background: $surface;
    }
    .ds-window-title {
        padding: 0 0 1 0;
    }
    .ds-content {
        padding: 0;
    }
    .ds-status {
        padding: 1 0 0 0;
        height: 1;
    }
    .ds-welcome {
        padding: 1;
    }
    """