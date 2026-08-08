"""paste_preview_screen.py — Workstream B: multi-line clipboard paste.

`action_paste_clipboard()` (Ctrl+V) used to collapse every pasted newline to
a space, because `#input-box` is a single-line `Input`. That's fine for a
short line, but it silently mangles anything with real structure — a pasted
code block, a multi-paragraph note, a log excerpt. This screen is the fix
for that half of Workstream B's spec ("add a multi-line paste path") without
migrating `#input-box` off `Input` (which `on_input_submitted`'s whole
dispatch chain — slash commands, tier-3 confirm, busy-subprocess forwarding,
`sov` prefix normalization — is tightly coupled to; a `TextArea` doesn't
raise `Input.Submitted` and reworking that dispatch chain was assessed as
much higher risk than this side-path).

When Ctrl+V (or a right-click, see `RippleInput.on_mouse_down`) detects
multi-line clipboard content, this pops up instead of collapsing: a
scrollable, EDITABLE `TextArea` pre-filled with the full text, Ctrl+Enter
(or the Send button) to dispatch it as a turn, Escape (or Cancel) to back
out untouched. Single-line clipboard content is completely unaffected —
same collapse-to-one-line behavior as before.

Mirrors CommandPaletteScreen's proven ModalScreen shape (Escape/q close,
lazy imports of anything from `.app` to avoid the exact circular-import
shape already found and fixed elsewhere this session).
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

MARK = "paste-plus-d"


class PastePreviewScreen(ModalScreen):
    """Ctrl+V / right-click paste of multi-line text: preview + edit, then
    send — instead of silently collapsing newlines to spaces."""

    BINDINGS = [
        Binding("escape", "cancel", "cancel", show=False),
        Binding("ctrl+enter", "send", "send", show=True, priority=True),
    ]

    def __init__(self, text: str) -> None:
        super().__init__()
        self._initial_text = text

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def action_send(self) -> None:
        area = self.query_one("#paste-preview-area", TextArea)
        text = area.text
        self.app.pop_screen()
        self.app._send_pasted_text(text)  # noqa: SLF001 — same-package cooperation

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "paste-send-btn":
            self.action_send()
        elif event.button.id == "paste-cancel-btn":
            self.action_cancel()

    def compose(self):
        line_count = self._initial_text.count("\n") + 1
        with Vertical(id="paste-modal"):
            yield Static(
                f"◊ Paste preview  [dim]({line_count} lines — edit if needed)[/dim]",
                id="paste-title",
            )
            yield TextArea(self._initial_text, id="paste-preview-area")
            with Horizontal(id="paste-btn-row"):
                yield Button("Send (Ctrl+Enter)", id="paste-send-btn", variant="success")
                yield Button("Cancel (Esc)", id="paste-cancel-btn", variant="error")

    DEFAULT_CSS = """
    PastePreviewScreen {
        align: center middle;
        background: $surface 60%;
    }
    #paste-modal {
        width: 90%;
        height: 85%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #paste-title { text-style: bold; margin-bottom: 1; height: 1; }
    #paste-preview-area { height: 1fr; margin-bottom: 1; }
    #paste-btn-row { height: 3; }
    #paste-btn-row Button { margin-right: 2; }
    """
