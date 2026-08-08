"""theme_picker_screen.py — Ctrl+T: an in-cockpit theme switcher.

Textual ships a built-in theme-switching command inside its default command
palette (normally Ctrl+P) — but this cockpit rebinds Ctrl+P to voice
push-to-talk (qol-voice-binding-d) and replaces the palette entirely with
its own CommandPaletteScreen (command-menu-d). That left no in-TUI way to
browse/change themes at all — `register_curated_themes`/`register_user_themes`
still register every theme correctly (cockpit/themes.py, cockpit/user_themes.py),
they just became unreachable from the UI. `sov theme list`/`sov theme set`
(the CLI path) still worked, which is why this went unnoticed for a while.

Deliberately a SEPARATE surface from the CLI `sov theme` command family —
this is the point-and-click picker; the CLI stays the scriptable path.

Mirrors CommandPaletteScreen's proven ModalScreen shape (Escape/q to close,
VerticalScroll body) with one addition the whole cockpit is retrofitting:
a visible "close" button, not just a keyboard escape hatch.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ThemeChoiceButton(Button):
    """A single theme option. Carries the real theme name separately from
    its (id-safe) widget id, since theme names may contain characters
    Textual ids don't allow."""

    def __init__(self, theme_name: str, *, current: bool) -> None:
        label = f"● {theme_name}" if current else f"  {theme_name}"
        safe_id = "theme-opt-" + "".join(
            c if (c.isalnum() or c == "-") else "-" for c in theme_name
        )
        super().__init__(label, id=safe_id, classes="theme-choice-btn")
        self.theme_name = theme_name


class ThemePickerScreen(ModalScreen):
    """Ctrl+T → browse every registered theme (curated + user-authored) and
    apply one with a click. The active theme is marked with ●."""

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
        current = getattr(self.app, "theme", None)
        names = sorted(getattr(self.app, "available_themes", {}).keys())

        with VerticalScroll(id="theme-modal"):
            with_close = Button("✕ close", id="theme-exit-btn")
            yield with_close
            yield Static(
                f"◊ Themes  [dim]({len(names)} available)[/dim]",
                id="theme-title",
            )
            yield Static(
                "[dim]Click a theme to apply it immediately. ● marks the "
                "current theme. Esc / q / ✕ to close.[/dim]",
                id="theme-help",
            )
            for name in names:
                yield ThemeChoiceButton(name, current=(name == current))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "theme-exit-btn":
            self.app.pop_screen()
            return
        theme_name = getattr(event.button, "theme_name", None)
        if not theme_name:
            return
        try:
            self.app.theme = theme_name
        except Exception:
            return
        try:
            from sovereign_agent.config import SETTINGS
            from . import user_themes as _ut
            _ut.set_active_theme_name(theme_name, SETTINGS.paths.data_dir)
        except Exception:
            pass  # persistence is best-effort; the live switch already applied
        self.app.pop_screen()

    DEFAULT_CSS = """
    ThemePickerScreen {
        align: center middle;
        background: $surface 60%;
    }
    #theme-modal {
        width: 60;
        height: 80%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #theme-exit-btn { width: 100%; margin-bottom: 1; }
    #theme-title { text-style: bold; margin-bottom: 1; }
    #theme-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #theme-modal .theme-choice-btn {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    """
