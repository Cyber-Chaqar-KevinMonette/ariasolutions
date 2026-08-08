"""game_studio_screen.py — the Game Studio: define game projects, set
focus, see her XP/level/storage at a glance.

Kevin's ask (2026-07-20): let Aria build video games toward real revenue
across up to 3 concurrent projects she can switch between but stays
disciplined on, with her point system visibly shown. Same clean shape as
the Bot Studio / Shop Studio (form + carousel), plus a header readout
that's the actual "make it visible" ask front and center.

Glyph choice deliberately sticks to sovereign_agent.glyphs' own SAFE
constants (◊ ✓ ✗ ▸ ◂) rather than emoji — this session's own glyph-
hardening work (is_emoji_risk()) exists specifically because emoji in
this exact kind of screen have broken on Kevin's terminal before; no
point introducing a fresh unverified instance of the same bug class in
brand-new code.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from sovereign_agent.game_projects import GameProject, GENRES, STARTER_IDEAS, save, validate
from sovereign_agent.glyphs import ARROW_LEFT, ARROW_RIGHT, CROSS, LOZENGE  # theme-studio-redesign-d


def cycle_index(idx: int, n: int, delta: int) -> int:
    if n <= 0:
        return 0
    return (idx + delta) % n


class GameStudioScreen(ModalScreen):
    """◊ Game Studio — define a game project, browse/edit/remove/focus. Esc to close."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
    ]

    def __init__(self, edit: GameProject | None = None) -> None:
        super().__init__()
        self._projects: list[GameProject] = []
        self._pi = 0
        self._edit = edit

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def _load_projects(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.game_projects import list_all
            self._projects = list_all(SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            self._projects = []

    def compose(self):
        self._load_projects()
        e = self._edit
        with VerticalScroll(id="game-modal"):
            with Horizontal(id="game-top"):
                yield Button(f"{CROSS} close", id="game-exit-btn")
                yield Button("save project", id="game-save-btn", variant="success")
            yield Static(f"{LOZENGE} Game Studio — define a project", id="game-title")
            yield Static("", id="game-status-header")
            if not self._projects:
                yield Static(
                    "[dim]starter ideas: " + " · ".join(STARTER_IDEAS) + "[/dim]",
                    id="game-starter-ideas",
                )
            yield Static("[dim]Name it, pick a genre, write the concept — save. "
                         "Esc to close.[/dim]", id="game-help")

            yield Label("Project name")
            yield Input(value=(e.project_name if e else ""), id="game-project-name",
                        placeholder="e.g. prestige-clicker")
            yield Label("Genre")
            yield Select([(label, key) for key, label in GENRES],
                         value=(e.genre if e else "idle-incremental"),
                         id="game-genre", allow_blank=False)
            yield Label("If 'Other', name the genre")
            yield Input(value=(e.genre_other if e else ""), id="game-genre-other",
                        placeholder="only if genre = Other")
            yield Label("Concept — what is this game?")
            yield Input(value=(e.concept if e else ""), id="game-concept",
                        placeholder="the loop, the hook, why it's worth finishing")
            yield Label("Monetization idea (optional)")
            yield Input(value=(e.monetization_note if e else ""), id="game-monetization")

            # ── browse existing projects ──
            yield Static("[dim]— your game projects —[/dim]", id="game-browse-sep")
            with Horizontal(classes="game-carousel"):
                yield Button(ARROW_LEFT, id="game-prev")
                yield Static("", id="game-project-label", classes="game-carousel-label")
                yield Button(ARROW_RIGHT, id="game-next")
            yield Label("Why switch focus to this one? (required to set focus)")
            yield Input(value="", id="game-focus-reason",
                        placeholder="e.g. Kevin asked to switch / vital: blocked on other project")
            with Horizontal(id="game-actions"):
                yield Button("edit", id="game-edit")
                yield Button("set as focus", id="game-set-focus", variant="primary")
                yield Button("remove", id="game-remove", variant="error")

    def on_mount(self) -> None:
        self._refresh_browse()
        self._refresh_status_header()

    def _refresh_status_header(self) -> None:
        """The 'make it visible' ask: focused project, level, XP, storage,
        most recent milestone screenshot — front and center."""
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.game_assets import check_workspace_budget
            from sovereign_agent.game_dev_xp import level_for_xp, progress_to_next, recent_events, total_xp
            from sovereign_agent.game_projects import game_workspace_dir, get_focus, load_by_slug

            data_dir = SETTINGS.paths.data_dir
            focus = get_focus(data_dir)
            xp = total_xp(data_dir=data_dir)
            level = level_for_xp(xp)
            within, per_level = progress_to_next(xp)

            if focus.slug:
                proj = load_by_slug(focus.slug, data_dir)
                focus_label = proj.project_name if proj else focus.slug
                try:
                    budget = check_workspace_budget(game_workspace_dir(focus.slug))
                    storage = f" · {budget.used_mb}MB/{budget.budget_mb}MB"
                except Exception:  # noqa: BLE001
                    storage = ""
            else:
                focus_label = "(none — set one below)"
                storage = ""

            events = recent_events(3, data_dir=data_dir)
            recent_line = ("; ".join(f"+{ev.xp} {ev.event_type}" for ev in events)
                          if events else "no XP events yet")

            header = (
                f"[b]Focused:[/b] {focus_label}{storage}\n"
                f"[b]Lv.{level}[/b] · XP {within}/{per_level} · recent: {recent_line}"
            )
            self.query_one("#game-status-header", Static).update(header)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_browse(self) -> None:
        try:
            lbl = self.query_one("#game-project-label", Static)
            if self._projects:
                p = self._projects[self._pi]
                lbl.update(f"[b]{p.project_name}[/b] — {p.genre_label} · {p.status}  "
                           f"[dim]({self._pi + 1}/{len(self._projects)})[/dim]")
            else:
                lbl.update("[dim](no projects yet — fill the form above and save)[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def _collect(self) -> GameProject:
        def v(wid: str) -> str:
            try:
                return self.query_one(f"#{wid}", Input).value.strip()
            except Exception:  # noqa: BLE001
                return ""
        genre = "idle-incremental"
        try:
            genre = str(self.query_one("#game-genre", Select).value or "idle-incremental")
        except Exception:  # noqa: BLE001
            pass
        return GameProject(
            project_name=v("game-project-name"), genre=genre,
            genre_other=v("game-genre-other"), concept=v("game-concept"),
            monetization_note=v("game-monetization"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "game-exit-btn":
            self.app.pop_screen(); return
        if bid == "game-save-btn":
            self._save(); return
        if bid == "game-prev" and self._projects:
            self._pi = cycle_index(self._pi, len(self._projects), -1); self._refresh_browse()
        elif bid == "game-next" and self._projects:
            self._pi = cycle_index(self._pi, len(self._projects), +1); self._refresh_browse()
        elif bid == "game-edit" and self._projects:
            self.app.pop_screen()
            self.app.push_screen(GameStudioScreen(edit=self._projects[self._pi]))
        elif bid == "game-set-focus" and self._projects:
            self._set_focus_current()
        elif bid == "game-remove" and self._projects:
            self._remove_current()

    def _save(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.game_projects import save as _save
        proj = self._collect()
        errs = validate(proj)
        if errs:
            self._toast(f"can't save: {errs[0]}"); return
        try:
            _save(proj, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"save failed: {type(exc).__name__}"); return
        self._toast(f"saved '{proj.project_name}' {LOZENGE}")
        self._load_projects(); self._refresh_browse(); self._refresh_status_header()

    def _set_focus_current(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.game_projects import set_focus, slugify
        proj = self._projects[self._pi]
        try:
            reason = self.query_one("#game-focus-reason", Input).value.strip()
        except Exception:  # noqa: BLE001
            reason = ""
        if not reason:
            self._toast("set-focus needs a reason — why switch to this project?")
            return
        try:
            set_focus(slugify(proj.project_name), reason, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"set-focus failed: {type(exc).__name__}: {exc}"); return
        self._toast(f"focus set: '{proj.project_name}'")
        self._refresh_status_header()

    def _remove_current(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.game_projects import delete
        name = self._projects[self._pi].project_name
        try:
            delete(name, SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        self._load_projects()
        self._pi = min(self._pi, max(0, len(self._projects) - 1))
        self._refresh_browse()
        self._toast(f"removed '{name}'")

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#game-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    GameStudioScreen { align: center middle; background: $surface 60%; }
    #game-modal {
        width: 76; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #game-top { height: 3; margin-bottom: 1; }
    #game-exit-btn { width: 1fr; margin-right: 1; }
    #game-save-btn { width: 1fr; }
    #game-title { text-style: bold; margin-bottom: 1; }
    #game-status-header { height: 3; margin-bottom: 1; color: $text; }
    #game-starter-ideas { margin-bottom: 1; }
    #game-help { height: 3; color: $text-muted; margin-bottom: 1; }
    GameStudioScreen Input, GameStudioScreen Select { width: 100%; margin-bottom: 1; }
    GameStudioScreen Label { color: $text-muted; }
    #game-browse-sep { margin-top: 1; }
    .game-carousel { height: 3; margin-bottom: 1; }
    .game-carousel Button { width: 6; }
    .game-carousel-label { width: 1fr; content-align: center middle; }
    #game-actions { height: 3; }
    #game-actions Button { width: 1fr; margin-right: 1; }
    """
