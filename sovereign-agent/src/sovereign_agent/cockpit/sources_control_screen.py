"""sources_control_screen.py — a control panel to turn tracker sources
on/off, per source or fleet-wide.

source-toggle-d (Kevin, 2026-07-27): "Make a control panel where I can
turn sources on and off. I want to toggle reddit off. But would like
that inside my control panel or another control panel if needed."
`Source.enabled` already existed and was already respected by
`BotRuntime.poll_once()` — nothing let an operator flip it. This screen
+ `discord_runtime.sources.set_source_enabled`/`set_reddit_sources_enabled`
close that gap. Mirrors the Stripe Links Vault's UX pattern.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Select, Static


class SourcesControlScreen(ModalScreen):
    """Sources control panel — per-source on/off, plus one-click "turn
    Reddit off" (this project, or the whole fleet). Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="sc-modal"):
            with Horizontal(id="sc-top"):
                yield Button("✕ close", id="sc-exit-btn")
                yield Button("reddit off (fleet)", id="sc-reddit-off-fleet-btn",
                            variant="error")
                yield Button("reddit on (fleet)", id="sc-reddit-on-fleet-btn")
            yield Static("Sources Control Panel — turn any tracker source "
                        "on or off", id="sc-title")
            yield Static(
                "[dim]Pick a project, then a source, then toggle it — or "
                "use the reddit buttons above for every reddit.com source "
                "at once.[/dim]", id="sc-help")
            yield Select([("(loading…)", "")], id="sc-which-project",
                        allow_blank=False)
            yield Select([("(pick a project)", "")], id="sc-which-source",
                        allow_blank=False)
            yield Static("", id="sc-info")
            with Horizontal(id="sc-actions"):
                yield Button("toggle this source", id="sc-toggle-btn",
                            variant="primary")
                yield Button("reddit off (this project)",
                            id="sc-reddit-off-project-btn")
            yield Static("[dim]— every source in this project —[/dim]",
                        id="sc-sep")
            yield Static("", id="sc-status")

    def on_mount(self) -> None:
        self._refresh_projects()
        self._refresh_sources()
        self._refresh_info()
        self._refresh_status()

    # ── data ──
    @staticmethod
    def _projects():
        from sovereign_agent.bot_projects import list_all
        from sovereign_agent.config import SETTINGS
        return list_all(SETTINGS.paths.data_dir)

    def _selected_project(self) -> str:
        try:
            return str(self.query_one("#sc-which-project", Select).value or "")
        except Exception:  # noqa: BLE001
            return ""

    def _selected_source(self) -> str:
        try:
            return str(self.query_one("#sc-which-source", Select).value or "")
        except Exception:  # noqa: BLE001
            return ""

    def _sources_for(self, project_name: str):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.discord_runtime.sources import list_sources
        return list_sources(SETTINGS.paths.data_dir, project_name)

    def _refresh_projects(self) -> None:
        try:
            projects = self._projects()
            sel = self.query_one("#sc-which-project", Select)
            if not projects:
                sel.set_options([("(no projects yet)", "")])
                return
            current = self._selected_project()
            names = {p.project_name for p in projects}
            options = [(p.project_name, p.project_name) for p in projects]
            sel.set_options(options)
            sel.value = current if current in names else options[0][1]
        except Exception:  # noqa: BLE001
            pass

    def _refresh_sources(self) -> None:
        try:
            proj = self._selected_project()
            sources = self._sources_for(proj) if proj else []
            sel = self.query_one("#sc-which-source", Select)
            if not sources:
                sel.set_options([("(no sources)", "")])
                return
            current = self._selected_source()
            names = {s.name for s in sources}
            options = [(f"{'✅' if s.enabled else '○'} {s.name} ({s.kind})", s.name)
                      for s in sources]
            sel.set_options(options)
            sel.value = current if current in names else options[0][1]
        except Exception:  # noqa: BLE001
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sc-which-project":
            self._refresh_sources()
            self._refresh_info()
            self._refresh_status()
        elif event.select.id == "sc-which-source":
            self._refresh_info()

    def _refresh_info(self) -> None:
        try:
            info = self.query_one("#sc-info", Static)
            proj, name = self._selected_project(), self._selected_source()
            source = next((s for s in self._sources_for(proj) if s.name == name),
                         None) if proj and name else None
            if source is None:
                info.update("[dim]no source selected[/dim]")
                return
            state = "[green]ON[/green]" if source.enabled else "[red]OFF[/red]"
            info.update(f"[b]{source.name}[/b] — {state}\n"
                        f"kind: {source.kind} · every "
                        f"{source.allowed_min_interval_s:.0f}s\n{source.url}")
        except Exception:  # noqa: BLE001
            pass

    def _refresh_status(self) -> None:
        try:
            proj = self._selected_project()
            sources = self._sources_for(proj) if proj else []
            lines = []
            for s in sources:
                icon = "✅" if s.enabled else "○"
                lines.append(f"{icon} {s.name} ({s.kind})")
            on_count = sum(1 for s in sources if s.enabled)
            lines.append(f"[dim]{on_count}/{len(sources)} source(s) on[/dim]")
            self.query_one("#sc-status", Static).update("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    # ── actions ──
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "sc-exit-btn":
            self.app.pop_screen()
        elif bid == "sc-toggle-btn":
            self._toggle_selected()
        elif bid == "sc-reddit-off-project-btn":
            self._reddit_toggle(enabled=False, fleet=False)
        elif bid == "sc-reddit-off-fleet-btn":
            self._reddit_toggle(enabled=False, fleet=True)
        elif bid == "sc-reddit-on-fleet-btn":
            self._reddit_toggle(enabled=True, fleet=True)

    def _toggle_selected(self) -> None:
        proj, name = self._selected_project(), self._selected_source()
        if not proj or not name:
            self._toast("pick a project and a source first")
            return
        source = next((s for s in self._sources_for(proj) if s.name == name), None)
        if source is None:
            self._toast(f"{name!r} not found")
            return
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.discord_runtime.sources import set_source_enabled
        set_source_enabled(SETTINGS.paths.data_dir, proj, name, not source.enabled)
        self._toast(f"{name} is now {'off' if source.enabled else 'on'}")
        self._refresh_sources(); self._refresh_info(); self._refresh_status()

    def _reddit_toggle(self, *, enabled: bool, fleet: bool) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.discord_runtime.sources import set_reddit_sources_enabled
        proj = None if fleet else self._selected_project()
        if not fleet and not proj:
            self._toast("pick a project first")
            return
        changed = set_reddit_sources_enabled(
            SETTINGS.paths.data_dir, enabled, project_name=proj)
        state = "on" if enabled else "off"
        total = sum(changed.values())
        scope = "fleet-wide" if fleet else proj
        self._toast(f"reddit {state}: {total} source(s) changed ({scope})"
                    if total else f"nothing to change ({scope})")
        self._refresh_sources(); self._refresh_info(); self._refresh_status()

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#sc-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    SourcesControlScreen { align: center middle; background: $surface 60%; }
    #sc-modal {
        width: 84; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #sc-top { height: 3; margin-bottom: 1; }
    #sc-top Button { width: 1fr; margin-right: 1; }
    #sc-title { text-style: bold; margin-bottom: 1; }
    #sc-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #sc-info { min-height: 4; margin-bottom: 1; color: $text; }
    SourcesControlScreen Select { width: 100%; margin-bottom: 1; }
    #sc-actions { height: 3; margin-bottom: 1; }
    #sc-actions Button { width: 1fr; margin-right: 1; }
    #sc-status { margin-top: 1; }
    """


__all__ = ["SourcesControlScreen"]
