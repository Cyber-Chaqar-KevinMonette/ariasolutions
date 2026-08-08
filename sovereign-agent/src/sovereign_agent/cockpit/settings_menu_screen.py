"""settings_menu_screen.py — the top-left gear @ menu: Settings + Help.

This is the DISTINCT counterpart to the bottom-left ⋮ "System Commands"
popup. Before this, the gear icon (Textual's HeaderIcon) and the ⋮ button
both opened the same CommandPaletteScreen — the "duplicate menus" bug.
Now the gear opens THIS (settings + help), and ⋮ opens system commands
only. Zero overlap.

Each item closes this menu and invokes the matching existing cockpit
action/screen — nothing here re-implements behavior, it just gathers the
settings + help entries behind one clearly-labeled surface.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from sovereign_agent.glyphs import ARROW_RIGHT, BULLET, LOZENGE, MIDDLE_DOT, SQUARE


class MenuItemButton(Button):
    """A settings/help menu row. `item_key` names which app action runs."""

    def __init__(self, label: str, item_key: str) -> None:
        super().__init__(label, id=f"settings-item-{item_key}",
                         classes="settings-item-btn")
        self.item_key = item_key


# (label, item_key) — order is display order within each section.
_SETTINGS_ITEMS: tuple[tuple[str, str], ...] = (
    # menu-split-2-d — Kevin's rule: @ is Settings + Help ONLY. Everything
    # else (J-Space, resume, modes, observatory, cosmic, workflows, legend)
    # lives in the ⋮ commands popup — no redundancy between the two menus.
    (f"{LOZENGE}  Theme picker", "theme"),
    (f"{SQUARE}  Layout", "layout"),
    (f"{ARROW_RIGHT}  Glyph picker", "glyphs"),
    (f"{BULLET}  Recording start/stop", "recording"),
)
_HELP_ITEMS: tuple[tuple[str, str], ...] = (
    ("?  Help overlay", "help"),
    ("⌨  Controls", "controls"),
    (f"{MIDDLE_DOT}  Changelog", "changelog"),
)


class SettingsMenuScreen(ModalScreen):
    """@ Settings & Help. Esc / q / ✕ to close; click an item to open it."""

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

    def compose(self):
        with VerticalScroll(id="settings-modal"):
            yield Button("✕ close", id="settings-exit-btn")
            yield Static("@ Settings & Help", id="settings-title")
            yield Static("[bold cyan]Settings[/bold cyan]")
            for label, key in _SETTINGS_ITEMS:
                yield MenuItemButton(label, key)
            yield Static("")
            yield Static("[bold cyan]Help[/bold cyan]")
            for label, key in _HELP_ITEMS:
                yield MenuItemButton(label, key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "settings-exit-btn":
            self.app.pop_screen()
            return
        key = getattr(event.button, "item_key", None)
        if key is None:
            return
        # Close this menu first, then run the target — every target either
        # pushes its own screen or acts on the base cockpit.
        self.app.pop_screen()
        self.app.run_settings_item(key)

    DEFAULT_CSS = """
    SettingsMenuScreen {
        align: center middle;
        background: $surface 60%;
    }
    #settings-modal {
        width: 48;
        height: 85%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #settings-exit-btn { width: 100%; margin-bottom: 1; }
    #settings-title { text-style: bold; margin-bottom: 1; }
    #settings-modal .settings-item-btn {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    """
