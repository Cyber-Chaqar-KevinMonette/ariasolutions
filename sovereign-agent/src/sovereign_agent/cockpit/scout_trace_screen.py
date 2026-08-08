"""scout_trace_screen.py — 🔎 watch HOW she gathers, live (Kevin's ask).

"Watch what she does, where she goes, how she gathers — and see her work
is valid and verified against grounded truth." This screen renders the
gather→link→verdict chain across every tracker, refreshed off the UI
thread (lesson 15).
"""
from __future__ import annotations

import asyncio

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from sovereign_agent.scout_verify import render_all_traces

REFRESH_S = 3.0


class ScoutTraceScreen(ModalScreen):
    """🔎 Scout Trace — how she gathers + grounded-truth proof. Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="st-modal"):
            with Horizontal(id="st-top"):
                yield Button("✕ close", id="st-exit-btn")
            yield Static("Scout Trace — how she gathers, live", id="st-title")
            yield Static("[dim]where she went, what she found, and whether it's "
                         "verified against the live page. ✓ verified · ◔ link "
                         "live · ! relay (source stands, page unreachable).[/dim]",
                         id="st-help")
            yield Static("collecting...", id="st-body")

    def on_mount(self) -> None:
        self._refreshing = False
        self._schedule_refresh()
        self.set_interval(REFRESH_S, self._schedule_refresh)

    def _schedule_refresh(self) -> None:
        if getattr(self, "_refreshing", False):
            return
        self._refreshing = True
        self.run_worker(self._collect_and_render(), exclusive=False)

    async def _collect_and_render(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            text = await asyncio.to_thread(
                render_all_traces, SETTINGS.paths.data_dir)
            try:
                self.query_one("#st-body", Static).update(text)
            except Exception:  # noqa: BLE001 — screen may be closing
                pass
        finally:
            self._refreshing = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "st-exit-btn":
            self.app.pop_screen()

    DEFAULT_CSS = """
    ScoutTraceScreen { align: center middle; background: $surface 60%; }
    #st-modal {
        width: 96; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #st-top { height: 3; margin-bottom: 1; }
    #st-exit-btn { width: 100%; }
    #st-title { text-style: bold; margin-bottom: 1; }
    #st-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #st-body { min-height: 10; }
    """
