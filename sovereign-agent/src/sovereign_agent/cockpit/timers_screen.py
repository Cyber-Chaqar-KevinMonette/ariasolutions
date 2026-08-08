"""timers_screen.py — ⧗ every live timer, visible (Kevin's ask).

Presence heartbeat, live work sessions, per-bot uptimes, per-source
next-poll countdowns, and queue retry/lease countdowns — elapsed vs
expected, with progress bars, auto-refreshing every 2s.

Lag discipline (lesson 15): the refresh timer NEVER touches disk on the UI
thread — collection runs via asyncio.to_thread; the timer callback only
schedules it and renders the last snapshot.
"""
from __future__ import annotations

import asyncio

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from sovereign_agent.timers import gather_timers, render_timers

REFRESH_S = 2.0


class TimersScreen(ModalScreen):
    """⧗ Timers — all her live countdowns. Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="tm-modal"):
            with Horizontal(id="tm-top"):
                yield Button("✕ close", id="tm-exit-btn")
            yield Static("⧗ Timers — her live countdowns", id="tm-title")
            yield Static("[dim]presence · live tasks · bot uptimes · next polls "
                         "· queue retries — refreshes every 2s[/dim]", id="tm-help")
            yield Static("collecting…", id="tm-body")

    def on_mount(self) -> None:
        self._refreshing = False
        self._schedule_refresh()
        self.set_interval(REFRESH_S, self._schedule_refresh)

    def _schedule_refresh(self) -> None:
        # timer callback: schedule only — no I/O on the UI thread (lesson 15)
        if getattr(self, "_refreshing", False):
            return
        self._refreshing = True
        self.run_worker(self._collect_and_render(), exclusive=False)

    async def _collect_and_render(self) -> None:
        try:
            rows = await asyncio.to_thread(gather_timers)
            text = render_timers(rows)
            try:
                self.query_one("#tm-body", Static).update(text)
            except Exception:  # noqa: BLE001 — screen may be closing
                pass
        finally:
            self._refreshing = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tm-exit-btn":
            self.app.pop_screen()

    DEFAULT_CSS = """
    TimersScreen { align: center middle; background: $surface 60%; }
    #tm-modal {
        width: 76; height: 85%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #tm-top { height: 3; margin-bottom: 1; }
    #tm-exit-btn { width: 100%; }
    #tm-title { text-style: bold; margin-bottom: 1; }
    #tm-help { height: 2; color: $text-muted; margin-bottom: 1; }
    #tm-body { min-height: 10; }
    """
