"""changelog_screen.py — the "Changelog / What's New" viewer.

Reached from the top-left Settings & Help menu, and via `/changelog`.
Reads the repo-root CHANGELOG.md and renders it scrollably. There is no
auto-updater (Aria is a local editable install), so "update" here means
"what changed / version notes" — the menu labels it "Changelog".
"""
from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .. import __version__


def _find_changelog() -> Path | None:
    """CHANGELOG.md lives at the repo root — three parents up from this
    module (src/sovereign_agent/cockpit/ -> repo root)."""
    here = Path(__file__).resolve()
    for base in (here.parents[3], here.parents[2]):
        candidate = base / "CHANGELOG.md"
        if candidate.is_file():
            return candidate
    return None


class ChangelogScreen(ModalScreen):
    """◊ Changelog → the version history, scrollable. Esc / q / ✕ to close."""

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
        if event.button.id == "changelog-exit-btn":
            event.stop()
            self.app.pop_screen()

    def compose(self):
        from rich.markup import escape

        with VerticalScroll(id="changelog-modal"):
            yield Button("✕ close", id="changelog-exit-btn")
            yield Static(
                f"◊ Changelog  [dim](you are on v{__version__})[/dim]",
                id="changelog-title",
            )
            path = _find_changelog()
            if path is None:
                yield Static(
                    "[dim]CHANGELOG.md not found next to the package.[/dim]",
                    id="changelog-body",
                )
                return
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                yield Static(
                    f"[dim](changelog unavailable: {type(exc).__name__})[/dim]",
                    id="changelog-body",
                )
                return
            # Render as escaped text so stray markup in the changelog can't
            # break the display; headings get a light touch of emphasis.
            lines = []
            for raw in text.splitlines():
                if raw.startswith("## "):
                    lines.append(f"[bold cyan]{escape(raw[3:])}[/bold cyan]")
                elif raw.startswith("# "):
                    lines.append(f"[bold]{escape(raw[2:])}[/bold]")
                else:
                    lines.append(escape(raw))
            yield Static("\n".join(lines), id="changelog-body")

    DEFAULT_CSS = """
    ChangelogScreen {
        align: center middle;
        background: $surface 60%;
    }
    #changelog-modal {
        width: 84;
        height: 85%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #changelog-exit-btn { width: 100%; margin-bottom: 1; }
    #changelog-title { text-style: bold; margin-bottom: 1; }
    #changelog-body { width: 100%; }
    """
