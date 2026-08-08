"""journal_screen.py — the J-Space, browsable: her reflections and yours.

Kevin's "nice J-Space." A scrollable modal that renders the journal
(`sovereign_agent.journal`) — her free reflections (🖊) and your notes (💬),
newest last. Read here; write with `/journal <your words>` (or ask her
"write in your journal: …"). Mirrors the ThemePicker modal shape.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class JournalScreen(ModalScreen):
    """◊ J-Space → the shared journal. Esc / q / ✕ to close."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
        Binding("q", "close", "close", show=False),
    ]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "journal-exit-btn":
            event.stop()
            self.app.pop_screen()

    def compose(self):
        from sovereign_agent.journal import recent_entries, render_journal

        with VerticalScroll(id="journal-modal"):
            yield Button("✕ close", id="journal-exit-btn")
            yield Static(
                "[dim]This is the J-Space — a place for reflections, not tasks. "
                "Write in it with `/journal <your words>`, or ask me "
                "“write in your journal: …”. Esc / q / ✕ to close.[/dim]",
                id="journal-help",
            )
            try:
                body = render_journal(recent_entries(limit=30))
            except Exception as exc:  # noqa: BLE001
                body = f"[dim](journal unavailable: {type(exc).__name__})[/dim]"
            yield Static(body, id="journal-body")

    DEFAULT_CSS = """
    JournalScreen {
        align: center middle;
        background: $surface 60%;
    }
    #journal-modal {
        width: 84;
        height: 85%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #journal-exit-btn { width: 100%; margin-bottom: 1; }
    #journal-help { height: 4; color: $text-muted; margin-bottom: 1; }
    #journal-body { width: 100%; }
    """
