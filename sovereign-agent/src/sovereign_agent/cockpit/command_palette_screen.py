"""command_palette_screen.py — Ctrl+M (or the "⋮ commands" button): a
scrollable popup listing every palette command in one place.

Workstream M: the palette used to permanently occupy 2-3 Horizontal rows
between the panes and the input box. Collapsing it into one button + this
popup reclaims that space for the observability/security/emotions strips
(see cockpit/app.py's palette-row patch) while keeping every command exactly
as reachable — same click-to-paste behavior, same reference-button actions
(legend/help/cosmic/workflows/rec/grow/demo), just paged behind one trigger.

Mirrors ApplyQueueScreen's proven ModalScreen shape (Escape/q to close,
VerticalScroll body) almost line for line — the fastest build in this plan
because the pattern is proven twice already (HelpScreen, ApplyQueueScreen).

PALETTE_COMMANDS/REFERENCE_BUTTONS/CommandButton are imported LAZILY inside
compose() rather than at module level: app.py imports CommandPaletteScreen,
so a module-level `from .app import ...` here would create the exact
circular-import shape found and fixed elsewhere this session (D/H2 vs
stewardship) — by the time compose() actually runs (screen-push time),
app.py has already finished loading, so the lazy import is always safe.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class CommandPaletteScreen(ModalScreen):
    """⋮ commands / Ctrl+M → every palette command, one scrollable list."""

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
        if event.button.id == "cp-exit-btn":
            event.stop()
            self.app.pop_screen()

    def compose(self):
        from .app import PALETTE_COMMANDS, REFERENCE_BUTTONS, CommandButton

        with VerticalScroll(id="cp-modal"):
            yield Button("✕ close", id="cp-exit-btn")
            yield Static(
                f"⋮ System Commands  [dim]({len(PALETTE_COMMANDS)} sov "
                f"commands · {len(REFERENCE_BUTTONS)} actions)[/dim]",
                id="cp-title",
            )
            yield Static(
                "[dim]Click a command to paste it into the input box (you "
                "review, then Enter). Settings & Help live in the top-left "
                "@ menu. Esc / q / ✕ to close.[/dim]",
                id="cp-help",
            )
            for palette_cmd in PALETTE_COMMANDS:
                yield CommandButton(palette_cmd)
            yield Static("[dim]— actions —[/dim]", id="cp-divider")
            for ref_cmd in REFERENCE_BUTTONS:
                yield CommandButton(ref_cmd)

    DEFAULT_CSS = """
    CommandPaletteScreen {
        align: center middle;
        background: $surface 60%;
    }
    #cp-modal {
        width: 72;
        height: 80%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #cp-exit-btn { width: 100%; margin-bottom: 1; }
    #cp-title { text-style: bold; margin-bottom: 1; }
    #cp-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #cp-modal CommandButton {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    #cp-divider { height: 1; }
    """
