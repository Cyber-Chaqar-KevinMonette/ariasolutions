"""controls_screen.py — the Controls reference (all keybindings, one menu).

Kevin asked to move the always-on footer key row off the front end into a
menu; the cockpit's `Footer` was removed and this screen replaces it.
Lists every key in CockpitApp.BINDINGS with a human label, grouped, so the
controls are one keystroke away without cluttering the panes.

Reached from the top-left Settings & Help menu and via F4.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

# Human descriptions + grouping for each bound key. Keyed by the action
# name used in CockpitApp.BINDINGS so this stays in sync structurally.
_GROUPS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("Session", (
        ("ctrl+q", "quit", "Quit the cockpit"),
        ("ctrl+h", "halt", "HALT — stop all autonomous work now"),
        ("ctrl+d", "disarm", "Disarm the kill switch / halt"),
        ("ctrl+l", "clear", "Clear the chat pane"),
    )),
    ("View & menus", (
        ("gear @", "Settings & Help", "Top-left icon — settings + help menu"),
        ("ctrl+m", "System commands", "Bottom-left ⋮ — sov command popup"),
        ("ctrl+t", "Theme picker", "Browse + apply a theme"),
        ("ctrl+o", "Layout", "Cycle the pane layout"),
        ("ctrl+g", "Glyphs", "Toggle the glyph picker strip"),
        ("ctrl+b", "Heart", "Cycle the status-bar heart"),
        ("f2", "Modes", "The crown — arm a mode"),
        ("f3", "Observatory", "Modes observability window"),
        ("f4", "Controls", "This screen"),
        ("f8", "Model", "Standard, sprint presets, or custom per-slot models"),
    )),
    ("Input & capture", (
        ("ctrl+v", "Paste", "Paste from the clipboard (with preview)"),
        ("ctrl+y", "Yank", "Copy the last turn"),
        ("ctrl+r", "Record", "Start / stop a screen recording"),
        ("ctrl+p", "Voice", "Push-to-talk voice input"),
    )),
    ("Help", (
        ("f1 / ?", "Help", "The help overlay"),
    )),
)


class ControlsScreen(ModalScreen):
    """⌨ Controls → every keybinding, grouped. Esc / q / ✕ to close."""

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
        if event.button.id == "controls-exit-btn":
            event.stop()
            self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="controls-modal"):
            yield Button("✕ close", id="controls-exit-btn")
            yield Static("⌨ Controls", id="controls-title")
            yield Static(
                "[dim]Every keybinding, one place. Esc / q / ✕ to close.[/dim]",
                id="controls-help",
            )
            for group_name, rows in _GROUPS:
                yield Static(f"[bold cyan]{group_name}[/bold cyan]")
                for key, label, desc in rows:
                    yield Static(
                        f"  [bold]{key:<10}[/bold] [b]{label}[/b]  "
                        f"[dim]{desc}[/dim]"
                    )
                yield Static("")

    DEFAULT_CSS = """
    ControlsScreen {
        align: center middle;
        background: $surface 60%;
    }
    #controls-modal {
        width: 76;
        height: 85%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #controls-exit-btn { width: 100%; margin-bottom: 1; }
    #controls-title { text-style: bold; margin-bottom: 1; }
    #controls-help { height: 2; color: $text-muted; margin-bottom: 1; }
    """
