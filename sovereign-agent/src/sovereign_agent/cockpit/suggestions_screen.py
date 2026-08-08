"""cockpit/suggestions_screen.py — "what should I work on?" — grounded.

Kevin, 2026-07-26: "a suggestions button... so when I want to ask her
for things she could or would like to work on, she can give me a list
of important and/or valuable task she can work on or practice doing."

Every row here comes straight from `work_suggestions.gather_suggestions()`
— real sentinel findings and real unbuilt bot-project ideas, nothing
invented. Picking one pastes `/work <goal>` into the input box for
review (propose, don't auto-act) — the same paste-not-send pattern
every other palette button already uses.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

MARK = "suggestions-d"

# Only show this many rows — a long tail of minor findings is still real,
# but the modal shouldn't need to scroll forever to find "use this".
MAX_SHOWN = 30


class SuggestionsScreen(ModalScreen):
    """✧ Grounded ideas for what to work on next — sourced live."""

    BINDINGS = [Binding("escape,q", "close_suggestions", "close")]

    CSS = """
    SuggestionsScreen { align: center middle; }
    #suggestions-modal {
        width: 96; max-height: 90%;
        background: $surface; border: round $primary;
        padding: 1 2;
        /* scrollbar-d (Kevin, 2026-07-26): same fix as my_inbox_screen —
           a short terminal could clip the button row off the bottom
           with no way to reach it. */
        overflow-y: auto;
    }
    #suggestions-title { text-style: bold; margin-bottom: 1; }
    #suggestions-help { color: $text-muted; margin-bottom: 1; }
    #suggestions-list { height: 16; border: round $primary 40%; margin-bottom: 1; }
    #suggestions-btn-row { height: 3; margin-bottom: 1; }
    #suggestions-btn-row Button { width: 1fr; margin-right: 1; }
    #suggestions-status { color: $text-muted; }
    """

    def action_close_suggestions(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="suggestions-modal"):
            yield Static("[b]✧ Suggestions — what's real and worth doing[/b]",
                        id="suggestions-title")
            yield Static(
                "[dim]Grounded in her own sentinel scans + unbuilt bot "
                "ideas — nothing invented. Select one, then Use it to "
                "paste /work <goal> for you to review and send.[/dim]",
                id="suggestions-help",
            )
            yield ListView(id="suggestions-list")
            with Vertical(id="suggestions-btn-row"):
                yield Button("use this — paste /work …", id="suggestions-use-btn",
                            variant="primary")
                yield Button("refresh", id="suggestions-refresh-btn")
            yield Static("", id="suggestions-status")

    def on_mount(self) -> None:
        self._items: list = []
        self._selected_index: int | None = None
        self._refresh_list()

    def _refresh_list(self) -> None:
        from rich.markup import escape
        from sovereign_agent.work_suggestions import gather_suggestions

        lv = self.query_one("#suggestions-list", ListView)
        lv.clear()
        self._selected_index = None
        try:
            self._items = gather_suggestions()
        except Exception as exc:  # noqa: BLE001
            self._items = []
            lv.append(ListItem(Label(
                f"[dim](suggestions unavailable: {type(exc).__name__})[/dim]")))
            return
        if not self._items:
            lv.append(ListItem(Label(
                "[dim]nothing concrete right now — every sentinel's clean "
                "and every named bot idea is built[/dim]")))
            return
        for s in self._items[:MAX_SHOWN]:
            line = f"{s.emoji} [{s.source}] {escape(s.summary)}"
            if s.remediation:
                line += f"  [dim]→ {escape(s.remediation)}[/dim]"
            lv.append(ListItem(Label(line)))
        if len(self._items) > MAX_SHOWN:
            lv.append(ListItem(Label(
                f"[dim]… and {len(self._items) - MAX_SHOWN} more — ask "
                f"'/suggestions' again after tending the top ones[/dim]")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#suggestions-list", ListView)
        idx = lv.index
        status = self.query_one("#suggestions-status", Static)
        if idx is not None and idx < len(self._items):
            self._selected_index = idx
            status.update(f"[dim]selected: {self._items[idx].summary[:60]}[/dim]")
        else:
            self._selected_index = None

    def on_button_pressed(self, event) -> None:
        bid = getattr(event.button, "id", "") or ""
        if bid == "suggestions-refresh-btn":
            self._refresh_list()
        elif bid == "suggestions-use-btn":
            self._use_selected()

    def _use_selected(self) -> None:
        status = self.query_one("#suggestions-status", Static)
        if self._selected_index is None or self._selected_index >= len(self._items):
            status.update("[yellow]select a suggestion first[/yellow]")
            return
        goal = self._items[self._selected_index].as_goal_text()
        self.app.pop_screen()
        try:
            input_box = self.app.query_one("#input-box", Input)
            input_box.value = f"/work {goal}"
            input_box.focus()
            try:
                input_box.cursor_position = len(input_box.value)
            except AttributeError:
                pass
        except Exception:  # noqa: BLE001
            pass


__all__ = ["SuggestionsScreen"]
