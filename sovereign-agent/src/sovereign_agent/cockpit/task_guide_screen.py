"""cockpit/task_guide_screen.py — "everything you can do with her."

Kevin, 2026-07-26: "Create a task guide button on the frontend so I can
see everything I can do with her and so I can test everything following
the guide."

Pure presentation over task_guide.py's grounded data — every capability
listed there is a real, registered tool (test_task_guide.py checks it).
Same big-scrollable-Static pattern as HelpScreen, just fed from data
instead of hand-typed prose, so it can never drift from what's real.
"""
from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

MARK = "task-guide-d"


def render_guide_text() -> str:
    from sovereign_agent.task_guide import CATEGORIES, total_tool_count

    lines: list[str] = [
        "[b]✧ Task Guide — everything you can do with her[/b]",
        "",
        "[dim]Pick a line, type or paste the example into the input box, "
        "press Enter. Every capability here is a real, live tool — "
        "nothing on this list is aspirational.[/dim]",
        "",
    ]
    for cat in CATEGORIES:
        lines.append(f"[bold cyan]{escape(cat.title)}[/bold cyan]")
        for entry in cat.entries:
            lines.append(f"  [b]{escape(entry.label)}[/b]")
            lines.append(f"    [green]> {escape(entry.example)}[/green]")
            if entry.note:
                lines.append(f"    [dim]{escape(entry.note)}[/dim]")
        lines.append("")
    try:
        total = total_tool_count()
        lines.append(
            f"[dim]This is the highlight reel — {total} tools are "
            f"registered in total. The rest are internal self-"
            f"improvement/architecture machinery, not things you'd "
            f"normally ask for directly. Ask her anything; if a tool "
            f"exists for it, she'll find it.[/dim]"
        )
    except Exception:  # noqa: BLE001 — the guide must never fail to render
        pass
    return "\n".join(lines)


class TaskGuideScreen(ModalScreen):
    """✧ The grounded capability menu — what she can do, and how to test it."""

    BINDINGS = [Binding("escape,q", "close_task_guide", "close")]

    CSS = """
    TaskGuideScreen { align: center middle; }
    #task-guide-modal {
        width: 96; max-height: 90%;
        background: $surface; border: round $primary;
        padding: 1 2;
        /* scrollbar-d (Kevin, 2026-07-26): a short terminal could clip
           the Close button off the bottom, below the inner scroll. */
        overflow-y: auto;
    }
    #task-guide-scroll { max-height: 34; }
    #task-guide-close { margin-top: 1; width: 100%; }
    """

    def action_close_task_guide(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        event.stop()
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="task-guide-modal"):
            with VerticalScroll(id="task-guide-scroll"):
                yield Static(render_guide_text(), id="task-guide-text")
            yield Button("✕  Close   (Esc / q)", id="task-guide-close",
                        variant="primary")


__all__ = ["TaskGuideScreen", "render_guide_text"]
