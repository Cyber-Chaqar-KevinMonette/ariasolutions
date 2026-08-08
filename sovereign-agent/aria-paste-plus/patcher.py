"""patcher.py — Workstream B: right-click / long-text paste in the chat box.

Two independent gaps in today's Ctrl+V (`action_paste_clipboard`), both named
directly in the plan:

1. Multi-line clipboard content gets collapsed to a single space-joined
   line before insertion, because `#input-box` is a single-line `Input`.
   Migrating `#input-box` itself to a multi-line `TextArea` was assessed
   as high risk — `on_input_submitted`'s entire dispatch chain (slash
   commands, tier-3 confirm, busy-subprocess forwarding, `sov` prefix
   normalization) keys off `Input.Submitted`, which a `TextArea` doesn't
   raise. Instead: when multi-line content is detected, pop a new
   `PastePreviewScreen` (own file, mirrors `CommandPaletteScreen`'s proven
   ModalScreen shape) with an editable `TextArea` — Ctrl+Enter/Send
   dispatches it as a real turn via a new `_send_pasted_text()` helper,
   Escape/Cancel backs out untouched. Single-line paste is byte-for-byte
   unchanged.
2. No right-click paste. `RippleInput` (the input box's own class) gets a
   small `on_mouse_down` handler that fires `action_paste_clipboard()` on
   `event.button == 3`. Textual's message-pump dispatch walks the full MRO
   per event (confirmed by reading `message_pump.py::_get_dispatch_methods`)
   and calls the widget's own class-level `on_mouse_down` (mine) IN
   ADDITION TO `Input`'s private `_on_mouse_down` (cursor placement) — so
   left-click cursor positioning is completely untouched by this addition.

Anchored span patches against the CURRENT live app.py (same discipline as
every other patcher this session — not a full-file replace).
"""
from __future__ import annotations

MARK = "paste-plus-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. import PastePreviewScreen (mirrors the CommandPaletteScreen import) ──

IMPORT_ANCHOR = (
    'try:  # command-menu-d\n'
    '    from .command_palette_screen import CommandPaletteScreen\n'
    'except Exception:  # pragma: no cover — command palette popup is strictly optional\n'
    '    CommandPaletteScreen = None  # type: ignore[assignment,misc]\n'
    '\n'
    'logger = logging.getLogger(__name__)\n'
)
IMPORT_NEW = (
    'try:  # command-menu-d\n'
    '    from .command_palette_screen import CommandPaletteScreen\n'
    'except Exception:  # pragma: no cover — command palette popup is strictly optional\n'
    '    CommandPaletteScreen = None  # type: ignore[assignment,misc]\n'
    '\n'
    f'try:  # {MARK}\n'
    '    from .paste_preview_screen import PastePreviewScreen\n'
    'except Exception:  # pragma: no cover — paste preview is strictly optional\n'
    '    PastePreviewScreen = None  # type: ignore[assignment,misc]\n'
    '\n'
    'logger = logging.getLogger(__name__)\n'
)


# ── 2. right-click paste on the input box itself ────────────────────────────

RIPPLE_INPUT_ANCHOR = (
    'class RippleInput(RippleBorderMixin, Input):\n'
    '    """The operator\'s command box. Its rounded border joins the living ripple in\n'
    '    every theme — a single-colour glow from the theme, or the rainbow Aurora\n'
    '    under a hue-cycling theme (per-theme opt-out via effects.ripple.widgets)."""\n'
)
RIPPLE_INPUT_NEW = (
    'class RippleInput(RippleBorderMixin, Input):\n'
    '    """The operator\'s command box. Its rounded border joins the living ripple in\n'
    '    every theme — a single-colour glow from the theme, or the rainbow Aurora\n'
    '    under a hue-cycling theme (per-theme opt-out via effects.ripple.widgets)."""\n'
    '\n'
    f'    def on_mouse_down(self, event) -> None:  # {MARK}\n'
    '        """Right-click (button 3) pastes the system clipboard, same as\n'
    '        Ctrl+V. Textual dispatches this alongside (not instead of)\n'
    '        Input\'s own private _on_mouse_down cursor-placement handler —\n'
    '        confirmed via message_pump.py\'s MRO-walking dispatch — so\n'
    '        normal left-click cursor positioning is unaffected."""\n'
    '        if event.button == 3 and self.app is not None:\n'
    '            self.app.action_paste_clipboard()\n'
)


# ── 3. multi-line-aware action_paste_clipboard + a new _send_pasted_text ───

PASTE_ACTION_ANCHOR = (
    '    def action_paste_clipboard(self) -> None:\n'
    '        """Paste system clipboard contents at the input box cursor.\n'
    '\n'
    "        Bound to Ctrl+V. Reads the clipboard via the platform's native\n"
    '        tooling (wl-paste on Wayland, xclip / xsel on X11, pbpaste on\n'
    '        macOS) and inserts at the current cursor position of the focused\n'
    '        Input widget. If no Input is focused, the operation is a no-op.\n'
    '\n'
    '        Multi-line clipboard contents have their newlines collapsed to\n'
    '        spaces (a chat-input convention; the operator can press Enter\n'
    '        to send and then paste the next line, or use Shift+Enter where\n'
    '        supported).\n'
    '        """\n'
    '        text = self._read_clipboard()\n'
    '        if not text:\n'
    '            self._write_meta("[dim](clipboard empty or unreadable)[/dim]")\n'
    '            return\n'
    '        # Collapse newlines for single-line input use\n'
    '        single_line = text.replace("\\r\\n", " ").replace("\\n", " ").rstrip()\n'
    '        try:\n'
    '            from textual.widgets import Input as _Input\n'
    '            input_box = self.query_one("#input-box", _Input)\n'
    '        except Exception:\n'
    '            return\n'
    '        input_box.insert_text_at_cursor(single_line)\n'
)
PASTE_ACTION_NEW = f'''    def action_paste_clipboard(self) -> None:
        """Paste system clipboard contents at the input box cursor.

        Bound to Ctrl+V. Reads the clipboard via the platform's native
        tooling (wl-paste on Wayland, xclip / xsel on X11, pbpaste on
        macOS) and inserts at the current cursor position of the focused
        Input widget. If no Input is focused, the operation is a no-op.

        {MARK} — multi-line clipboard contents no longer collapse to a
        single space-joined line. Instead a PastePreviewScreen pops up
        with the full text in an editable TextArea (Ctrl+Enter/Send to
        dispatch it as a real turn, Escape/Cancel to back out untouched)
        so pasted code/notes/log excerpts keep their structure. Single-
        line content is unaffected — same collapse-and-insert behavior.
        """
        text = self._read_clipboard()
        if not text:
            self._write_meta("[dim](clipboard empty or unreadable)[/dim]")
            return
        normalized = text.replace("\\r\\n", "\\n").rstrip("\\n")
        if "\\n" in normalized and PastePreviewScreen is not None:
            self.push_screen(PastePreviewScreen(normalized))
            return
        # Single-line (or PastePreviewScreen unavailable): collapse as before.
        single_line = text.replace("\\r\\n", " ").replace("\\n", " ").rstrip()
        try:
            from textual.widgets import Input as _Input
            input_box = self.query_one("#input-box", _Input)
        except Exception:
            return
        input_box.insert_text_at_cursor(single_line)

    def _send_pasted_text(self, text: str) -> None:  # {MARK}
        """Dispatch text confirmed/edited in PastePreviewScreen as a real
        turn. Slash commands still take the slash-command path (mirrors
        on_input_submitted's own top-priority rule); everything else goes
        straight to the conversation pipeline."""
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            self._handle_slash(text)
            return
        self._dispatch_turn(text)
'''


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, IMPORT_ANCHOR, IMPORT_NEW, label="import anchor")
    text = _replace_once(text, RIPPLE_INPUT_ANCHOR, RIPPLE_INPUT_NEW, label="RippleInput anchor")
    text = _replace_once(text, PASTE_ACTION_ANCHOR, PASTE_ACTION_NEW, label="paste action anchor")
    return text, True
