"""discord_watch_screen.py — ⌁ watch her work Discord, live (Kevin's ask).

Her whole shift in one window: is the duty loop alive, is the bot on the
gateway, presence, the attention queue, today's counts — and the rolling
feed of everything she does and learns (customers answered, probes
deflected, alerts delivered, members welcomed, ads posted, lessons
recorded, sources going bad).

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

from sovereign_agent.discord_watch import render_activity

REFRESH_S = 2.0


class DiscordWatchScreen(ModalScreen):
    """⌁ Discord Watch — her live shift. Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="dw-modal"):
            with Horizontal(id="dw-top"):
                yield Button("✕ close", id="dw-exit-btn")
            yield Static("⌁ Discord Watch — her shift, live", id="dw-title")
            yield Static("[dim]everything she does and learns on Discord — "
                         "customers, deliveries, welcomes, ads, lessons. "
                         "Run her shift: `sov shop duty --live` · speak to "
                         "the server: /server-message[/dim]", id="dw-help")
            yield Static("collecting...", id="dw-body")

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
            text = await asyncio.to_thread(render_activity, None, limit=40)
            try:
                self.query_one("#dw-body", Static).update(text)
            except Exception:  # noqa: BLE001 — screen may be closing
                pass
        finally:
            self._refreshing = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dw-exit-btn":
            self.app.pop_screen()

    DEFAULT_CSS = """
    DiscordWatchScreen { align: center middle; background: $surface 60%; }
    #dw-modal {
        width: 90; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #dw-top { height: 3; margin-bottom: 1; }
    #dw-exit-btn { width: 100%; }
    #dw-title { text-style: bold; margin-bottom: 1; }
    #dw-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #dw-body { min-height: 10; }
    """
