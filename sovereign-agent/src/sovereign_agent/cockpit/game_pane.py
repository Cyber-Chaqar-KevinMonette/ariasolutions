"""game_pane.py — the ✦ godot split-pane: quick actions for the Game
Studio's Godot toolset, mirroring movie_pane.py/screen_studio_pane.py's
proven pattern.

Kevin (2026-08-02): "extend her list of tools and wire the tools. Prepare
her for game design inside of Godot... start with 2D or 2.5D and then
work our way to 3D." A real gap: Game Studio (game_studio_screen.py) is
modal-only (define/edit/browse/focus) — unlike Movie Studio, there was no
persistent quick-action panel for the actual build loop (scaffold the
real project, check it, open the editor, export). This is that panel.

Deliberately NOT the same button as game-toggle-btn/action_toggle_game_window
-- that toggles an unrelated feature (the #game-window XP/income/token
stats display), confirmed by reading its own code before wiring this.
"""
from __future__ import annotations

from textual import work
from textual.containers import VerticalScroll
from textual.widgets import Button, Static

__all__ = ["GamePane"]


class GamePane(VerticalScroll):
    """Quick actions for the focused game project's Godot toolset."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Same busy-guard idiom as MoviePane/ScreenStudioPane._busy.
        self._busy: set[str] = set()

    def _try_start(self, group: str) -> bool:
        if group in self._busy:
            self._toast("still working — wait for it to finish first")
            return False
        self._busy.add(group)
        return True

    def _finish(self, group: str) -> None:
        self._busy.discard(group)

    def compose(self):
        yield Static("", id="game-pane-header")
        yield Static("", id="game-pane-status")
        yield Button("Browse / Switch / New Project", id="game-pane-new-project")
        yield Button("Pause Project", id="game-pane-pause")
        yield Button("Scaffold Godot Project", id="game-pane-scaffold")
        yield Button("Check", id="game-pane-check")
        yield Button("Open in Editor", id="game-pane-open")
        yield Button("Award XP: Milestone", id="game-pane-xp")

    def on_mount(self) -> None:
        self.refresh_all()

    def refresh_all(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.game_projects import get_focus, load_by_slug

            focus = get_focus(SETTINGS.paths.data_dir)
            project = load_by_slug(focus.slug, SETTINGS.paths.data_dir) if focus.slug else None
            if project:
                label = (f"◊ Game Studio — focused: {project.project_name} "
                        f"({project.dimension}, {project.engine}) · {project.status}")
            elif focus.slug:
                label = f"◊ Game Studio — focused: {focus.slug}"
            else:
                label = "◊ Game Studio — no project focused yet"
            self.query_one("#game-pane-header", Static).update(label)
            try:
                pause_btn = self.query_one("#game-pane-pause", Button)
                pause_btn.label = ("Resume Project" if project and project.status == "paused"
                                   else "Pause Project")
                pause_btn.disabled = project is None
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#game-pane-status", Static).update(msg)
        except Exception:  # noqa: BLE001
            pass

    def _focused_slug(self) -> str | None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.game_projects import get_focus
        return get_focus(SETTINGS.paths.data_dir).slug

    # ── button dispatch ──────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.button.add_class("flash")
        self.set_timer(0.3, lambda: event.button.remove_class("flash"))

        bid = event.button.id
        if bid == "game-pane-new-project":
            self.app.action_game_studio(); return
        if bid == "game-pane-pause":
            self._toggle_pause(); return
        if bid == "game-pane-scaffold":
            self._scaffold(); return
        if bid == "game-pane-check":
            self._check(); return
        if bid == "game-pane-open":
            self._open_editor(); return
        if bid == "game-pane-xp":
            self._award_xp(); return

    # ── actions ──────────────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        """Pause/resume the focused project's status. A plain local JSON
        read+write (game_projects.save()) — no subprocess/network, so no
        @work thread worker needed, unlike the tool-backed actions below."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.events import emit_event
        from sovereign_agent.game_projects import load_by_slug, save

        slug = self._focused_slug()
        if not slug:
            self._toast("no project focused — open Game Studio to focus one first")
            return
        project = load_by_slug(slug, SETTINGS.paths.data_dir)
        if project is None:
            self._toast(f"focused project {slug!r} not found on disk")
            return
        if project.status == "paused":
            project.status = "active"
            self._toast(f"resumed {project.project_name!r}")
            flag = "game-resume-d"
        else:
            project.status = "paused"
            self._toast(f"paused {project.project_name!r}")
            flag = "game-pause-d"
        save(project, SETTINGS.paths.data_dir)
        # observability-gap-fix-d (quality sentinel, 2026-08-02): every
        # sibling action in this pane goes through a tool's own event
        # emission; this one was a raw local mutation with no event at
        # all — closing that gap.
        emit_event(flag, plane="control", trace_id=f"game-pane-{slug}",
                  payload={"project": project.project_name, "status": project.status})
        self.refresh_all()

    def _scaffold(self) -> None:
        slug = self._focused_slug()
        if not slug:
            self._toast("no project focused — open Game Studio to focus one first")
            return
        if not self._try_start("game-pane-scaffold"):
            return
        self._toast(f"scaffolding {slug}…")
        self._scaffold_worker(slug)

    @work(thread=True, exclusive=True, group="game-pane-scaffold")
    def _scaffold_worker(self, slug: str) -> None:
        import asyncio

        from sovereign_agent.tools.scaffold_godot_project import ScaffoldGodotProjectTool

        tool = ScaffoldGodotProjectTool()
        result = asyncio.run(
            tool.execute(tool.Args(project_slug=slug), trace_id="game-pane-scaffold")
        )
        msg = result.output["message"] if result.ok else f"scaffold failed: {result.error}"
        self.app.call_from_thread(self._toast, msg)
        self.app.call_from_thread(self._finish, "game-pane-scaffold")

    def _check(self) -> None:
        slug = self._focused_slug()
        if not slug:
            self._toast("no project focused — open Game Studio to focus one first")
            return
        if not self._try_start("game-pane-check"):
            return
        self._toast(f"checking {slug}…")
        self._check_worker(slug)

    @work(thread=True, exclusive=True, group="game-pane-check")
    def _check_worker(self, slug: str) -> None:
        import asyncio

        from sovereign_agent.resilience import guarded_execute
        from sovereign_agent.tools.godot_check import GodotCheckTool

        # resilience-cockpit-gate-d — this pane calls the tool directly
        # (not through loop.py's own LLM-driven dispatch gate), so it needs
        # its own breaker coverage: a hung/failing godot subprocess
        # shouldn't be retried unboundedly just because a human keeps
        # clicking Check.
        tool = GodotCheckTool()
        result = asyncio.run(
            guarded_execute(tool, tool.Args(project_slug=slug),
                            trace_id="game-pane-check",
                            breaker_name="tool:godot_check")
        )
        msg = "✓ check passed, no errors" if result.ok else f"check failed: {result.error}"
        self.app.call_from_thread(self._toast, msg)
        self.app.call_from_thread(self._finish, "game-pane-check")

    def _open_editor(self) -> None:
        slug = self._focused_slug()
        if not slug:
            self._toast("no project focused — open Game Studio to focus one first")
            return
        if not self._try_start("game-pane-open"):
            return
        self._toast(f"opening {slug} in the Godot editor…")
        self._open_editor_worker(slug)

    @work(thread=True, exclusive=True, group="game-pane-open")
    def _open_editor_worker(self, slug: str) -> None:
        import asyncio

        from sovereign_agent.tools.godot_open import GodotOpenTool

        tool = GodotOpenTool()
        result = asyncio.run(
            tool.execute(tool.Args(project_slug=slug), trace_id="game-pane-open")
        )
        msg = (result.output.get("message", "opened") if result.ok
               else f"open failed: {result.error}")
        self.app.call_from_thread(self._toast, msg)
        self.app.call_from_thread(self._finish, "game-pane-open")

    def _award_xp(self) -> None:
        slug = self._focused_slug()
        if not slug:
            self._toast("no project focused — open Game Studio to focus one first")
            return
        if not self._try_start("game-pane-xp"):
            return
        self._award_xp_worker(slug)

    @work(thread=True, exclusive=True, group="game-pane-xp")
    def _award_xp_worker(self, slug: str) -> None:
        import asyncio

        from sovereign_agent.tools.award_game_xp import AwardGameXPTool

        tool = AwardGameXPTool()
        result = asyncio.run(
            tool.execute(
                tool.Args(project_slug=slug, event_type="milestone",
                          note="milestone recorded from the Game Studio pane"),
                trace_id="game-pane-xp",
            )
        )
        msg = "✓ milestone XP recorded" if result.ok else f"XP award failed: {result.error}"
        self.app.call_from_thread(self._toast, msg)
        self.app.call_from_thread(self._finish, "game-pane-xp")

    # Base state is hidden — #main.game-split (cockpit/app.py) reveals +
    # widths it. TYPE selector (not id) for self-styling — the known
    # Textual gotcha movie_pane.py's own comment documents.
    DEFAULT_CSS = """
    GamePane {
        display: none;
        border-left: solid $primary;
        padding: 0 1;
        background: $surface;
    }
    #game-pane-header { height: auto; text-style: bold; margin-bottom: 1; }
    #game-pane-status {
        height: auto; min-height: 3; color: $text; text-style: bold;
        margin-bottom: 1; padding: 0 1; border: round $primary;
    }
    GamePane Button { width: 100%; margin-bottom: 1; }
    GamePane Button.flash { border: round $success; background: $success 20%; color: $success; }
    """
