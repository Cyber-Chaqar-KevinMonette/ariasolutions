"""movie_studio_screen.py — the Movie Studio: define movie projects, set
focus, generate storyboards, draft original pitches, see her XP/level/
storage at a glance.

movie-studio-d (Kevin, 2026-07-28): "Let's add a movie producer mode...
get her producing full scale movies." Same clean shape as Game Studio
(form + carousel + a live status header) plus two real, new action rows:
generating a storyboard still (composes the real image-gen tool) and
drafting original pitch concepts (the Dream Pitch Generator — "AI dreams
of the future... whatever draws attention").

Glyph choice deliberately sticks to sovereign_agent.glyphs' own SAFE
constants, same discipline as game_studio_screen.py.

Heavy work (real diffusion generation) runs in a background worker
thread (mirrors app.py's `_demo_worker`/`_captest_worker` pattern) so the
UI never freezes waiting on the GPU. Drafting pitches is fast/local (pure
planning + a continuation record, no LLM call from this screen directly)
so it runs inline, same as save/set-focus/remove.
"""
from __future__ import annotations

import asyncio

from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from sovereign_agent.movie_projects import MOVIE_GENRES, MovieProject, STARTER_IDEAS, save, validate
from sovereign_agent.glyphs import ARROW_LEFT, ARROW_RIGHT, CROSS, LOZENGE


def cycle_index(idx: int, n: int, delta: int) -> int:
    if n <= 0:
        return 0
    return (idx + delta) % n


class MovieStudioScreen(ModalScreen):
    """◊ Movie Studio — define a movie project, browse/edit/remove/focus,
    generate storyboards, draft pitches. Esc to close."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
    ]

    def __init__(self, edit: MovieProject | None = None) -> None:
        super().__init__()
        self._projects: list[MovieProject] = []
        self._pi = 0
        self._edit = edit
        # Hardening pass (Kevin, 2026-07-28) — same real bug found in
        # movie_pane.py: @work(exclusive=True, thread=True) only cancels a
        # worker's bookkeeping, not the actual running Python thread, so a
        # stale completion toast can land after a newer one's. Explicit
        # per-group busy guard instead of relying on exclusive= alone.
        self._busy: set[str] = set()

    def _try_start(self, group: str) -> bool:
        if group in self._busy:
            self._toast("still working on the previous action — wait for it to finish first")
            return False
        self._busy.add(group)
        return True

    def _finish(self, group: str) -> None:
        self._busy.discard(group)

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def _load_projects(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_projects import list_all
            self._projects = list_all(SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            self._projects = []

    def compose(self):
        self._load_projects()
        e = self._edit
        with VerticalScroll(id="movie-modal"):
            with Horizontal(id="movie-top"):
                yield Button(f"{CROSS} close", id="movie-exit-btn")
                yield Button("save project", id="movie-save-btn", variant="success")
            yield Static(f"{LOZENGE} Movie Studio — define a project", id="movie-title")
            yield Static("", id="movie-status-header")
            if not self._projects:
                yield Static(
                    "[dim]starter ideas: " + " · ".join(STARTER_IDEAS) + "[/dim]",
                    id="movie-starter-ideas",
                )
            yield Static("[dim]Title it, pick a genre, write the logline — save. "
                         "Esc to close.[/dim]", id="movie-help")

            yield Label("Title")
            yield Input(value=(e.title if e else ""), id="movie-title-input",
                       placeholder="e.g. Test Film")
            yield Label("Genre")
            yield Select([(label, key) for key, label in MOVIE_GENRES],
                         value=(e.genre if e else "short-film"),
                         id="movie-genre", allow_blank=False)
            yield Label("If 'Other', name the genre")
            yield Input(value=(e.genre_other if e else ""), id="movie-genre-other",
                       placeholder="only if genre = Other")
            yield Label("Logline — the one-line pitch")
            yield Input(value=(e.logline if e else ""), id="movie-logline",
                       placeholder="who, wants what, why it matters")
            yield Label("Style")
            yield Select([("Animated", "animated"), ("Live-action", "live-action"),
                         ("Mixed", "mixed"), ("Other", "other")],
                         value=(e.style if e else "animated"),
                         id="movie-style", allow_blank=False)
            yield Label("Monetization idea (optional)")
            yield Input(value=(e.monetization_note if e else ""), id="movie-monetization")

            # ── browse existing projects ──
            yield Static("[dim]— your movie projects —[/dim]", id="movie-browse-sep")
            with Horizontal(classes="movie-carousel"):
                yield Button(ARROW_LEFT, id="movie-prev")
                yield Static("", id="movie-project-label", classes="movie-carousel-label")
                yield Button(ARROW_RIGHT, id="movie-next")
            yield Label("Why switch focus to this one? (required to set focus)")
            yield Input(value="", id="movie-focus-reason",
                       placeholder="e.g. Kevin asked to switch / vital: blocked on other project")
            with Horizontal(id="movie-actions"):
                yield Button("edit", id="movie-edit")
                yield Button("set as focus", id="movie-set-focus", variant="primary")
                yield Button("remove", id="movie-remove", variant="error")

            # ── real generation actions ──
            yield Static("[dim]— generate for the browsed project —[/dim]",
                        id="movie-gen-sep")
            yield Label("Storyboard prompt")
            yield Input(value="", id="movie-storyboard-prompt",
                       placeholder="the shot/scene to draw")
            yield Button("generate storyboard", id="movie-gen-storyboard")
            yield Label("Clip prompt (real, local — slow: ~1-3 min on this hardware)")
            yield Input(value="", id="movie-clip-prompt",
                       placeholder="the shot/scene to animate")
            yield Button("generate clip", id="movie-gen-clip")
            yield Label("Pitch theme (optional — blank = open/attention-grabbing)")
            yield Input(value="", id="movie-pitch-theme",
                       placeholder="e.g. hopeful AI futures — or leave blank")
            yield Button("draft pitches", id="movie-draft-pitches")

    def on_mount(self) -> None:
        self._refresh_browse()
        self._refresh_status_header()

    def _refresh_status_header(self) -> None:
        """The 'make it visible' ask: focused project, level, XP, storage,
        recent XP events — front and center."""
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_assets import check_workspace_budget
            from sovereign_agent.movie_dev_xp import level_for_xp, progress_to_next, recent_events, total_xp
            from sovereign_agent.movie_projects import get_focus, load_by_slug, movie_workspace_dir

            data_dir = SETTINGS.paths.data_dir
            focus = get_focus(data_dir)
            xp = total_xp(data_dir=data_dir)
            level = level_for_xp(xp)
            within, per_level = progress_to_next(xp)

            if focus.slug:
                proj = load_by_slug(focus.slug, data_dir)
                focus_label = proj.title if proj else focus.slug
                try:
                    budget = check_workspace_budget(movie_workspace_dir(focus.slug))
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
            self.query_one("#movie-status-header", Static).update(header)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_browse(self) -> None:
        try:
            lbl = self.query_one("#movie-project-label", Static)
            if self._projects:
                p = self._projects[self._pi]
                lbl.update(f"[b]{p.title}[/b] — {p.genre_label} · {p.status}  "
                          f"[dim]({self._pi + 1}/{len(self._projects)})[/dim]")
            else:
                lbl.update("[dim](no projects yet — fill the form above and save)[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def _collect(self) -> MovieProject:
        def v(wid: str) -> str:
            try:
                return self.query_one(f"#{wid}", Input).value.strip()
            except Exception:  # noqa: BLE001
                return ""
        genre = "short-film"
        try:
            genre = str(self.query_one("#movie-genre", Select).value or "short-film")
        except Exception:  # noqa: BLE001
            pass
        style = "animated"
        try:
            style = str(self.query_one("#movie-style", Select).value or "animated")
        except Exception:  # noqa: BLE001
            pass
        return MovieProject(
            title=v("movie-title-input"), genre=genre,
            genre_other=v("movie-genre-other"), logline=v("movie-logline"),
            style=style, monetization_note=v("movie-monetization"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "movie-exit-btn":
            self.app.pop_screen(); return
        if bid == "movie-save-btn":
            self._save(); return
        if bid == "movie-prev" and self._projects:
            self._pi = cycle_index(self._pi, len(self._projects), -1); self._refresh_browse()
        elif bid == "movie-next" and self._projects:
            self._pi = cycle_index(self._pi, len(self._projects), +1); self._refresh_browse()
        elif bid == "movie-edit" and self._projects:
            self.app.pop_screen()
            self.app.push_screen(MovieStudioScreen(edit=self._projects[self._pi]))
        elif bid == "movie-set-focus" and self._projects:
            self._set_focus_current()
        elif bid == "movie-remove" and self._projects:
            self._remove_current()
        elif bid == "movie-gen-storyboard":
            self._generate_storyboard_current()
        elif bid == "movie-gen-clip":
            self._generate_clip_current()
        elif bid == "movie-draft-pitches":
            self._draft_pitches_current()

    def _save(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_projects import save as _save
        proj = self._collect()
        errs = validate(proj)
        if errs:
            self._toast(f"can't save: {errs[0]}"); return
        try:
            _save(proj, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"save failed: {type(exc).__name__}"); return
        self._toast(f"saved '{proj.title}' {LOZENGE}")
        self._load_projects(); self._refresh_browse(); self._refresh_status_header()

    def _set_focus_current(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_projects import set_focus, slugify
        proj = self._projects[self._pi]
        try:
            reason = self.query_one("#movie-focus-reason", Input).value.strip()
        except Exception:  # noqa: BLE001
            reason = ""
        if not reason:
            self._toast("set-focus needs a reason — why switch to this project?")
            return
        try:
            set_focus(slugify(proj.title), reason, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"set-focus failed: {type(exc).__name__}: {exc}"); return
        self._toast(f"focus set: '{proj.title}'")
        self._refresh_status_header()

    def _remove_current(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_projects import delete
        title = self._projects[self._pi].title
        try:
            delete(title, SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        self._load_projects()
        self._pi = min(self._pi, max(0, len(self._projects) - 1))
        self._refresh_browse()
        self._toast(f"removed '{title}'")

    # ── real generation actions ─────────────────────────────────────────

    def _generate_storyboard_current(self) -> None:
        if not self._projects:
            self._toast("no project browsed — save one first"); return
        proj = self._projects[self._pi]
        try:
            prompt = self.query_one("#movie-storyboard-prompt", Input).value.strip()
        except Exception:  # noqa: BLE001
            prompt = ""
        if not prompt:
            self._toast("storyboard needs a prompt — describe the shot/scene")
            return
        if not self._try_start("moviestudio-storyboard"):
            return
        from sovereign_agent.movie_projects import slugify
        slug = slugify(proj.title)
        self._toast(f"generating storyboard for '{proj.title}' — this can take a while…")
        self._storyboard_worker(slug, prompt, proj.title)

    @work(thread=True, exclusive=True, group="moviestudio-storyboard")
    def _storyboard_worker(self, slug: str, prompt: str, title: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_generate_storyboard

        def _on_wait(available_mb, elapsed) -> None:
            self.app.call_from_thread(
                self._toast,
                f"please wait — movie studio vision model is loading, "
                f"waiting for system RAM to clear ({elapsed:.0f}s, {available_mb}MB available)…",
            )

        try:
            try:
                message = asyncio.run(run_generate_storyboard(slug, prompt, on_wait=_on_wait))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(
                    self._toast, f"storyboard generation error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, f"'{title}': {message}")
            self.app.call_from_thread(self._refresh_status_header)
        finally:
            self._finish("moviestudio-storyboard")

    def _generate_clip_current(self) -> None:
        if not self._projects:
            self._toast("no project browsed — save one first"); return
        proj = self._projects[self._pi]
        try:
            prompt = self.query_one("#movie-clip-prompt", Input).value.strip()
        except Exception:  # noqa: BLE001
            prompt = ""
        if not prompt:
            self._toast("clip needs a prompt — describe the shot/scene")
            return
        if not self._try_start("moviestudio-clip"):
            return
        from sovereign_agent.movie_projects import slugify
        slug = slugify(proj.title)
        self._toast(f"generating clip for '{proj.title}' — real, local, slow "
                   f"(~1-3 min on this hardware)…")
        self._clip_worker(slug, prompt, proj.title)

    @work(thread=True, exclusive=True, group="moviestudio-clip")
    def _clip_worker(self, slug: str, prompt: str, title: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_generate_clip

        def _on_wait(available_mb, elapsed) -> None:
            self.app.call_from_thread(
                self._toast,
                f"please wait — movie studio vision model is loading, "
                f"waiting for system RAM to clear ({elapsed:.0f}s, {available_mb}MB available)…",
            )

        try:
            try:
                message = asyncio.run(run_generate_clip(slug, prompt, on_wait=_on_wait))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(
                    self._toast, f"clip generation error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, f"'{title}': {message}")
            self.app.call_from_thread(self._refresh_status_header)
        finally:
            self._finish("moviestudio-clip")

    def _draft_pitches_current(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.continuation import ContinuationStore
        from sovereign_agent.planners import get_planner
        from sovereign_agent.planners.base import PlannerError

        try:
            theme = self.query_one("#movie-pitch-theme", Input).value.strip()
        except Exception:  # noqa: BLE001
            theme = ""

        import time
        output = (SETTINGS.paths.sandbox_dir / "movie_pitches"
                 / f"pitches-{int(time.time())}.md")
        output.parent.mkdir(parents=True, exist_ok=True)

        planner = get_planner("movie-pitch")
        try:
            plan_kwargs = {"output": str(output)}
            if theme:
                plan_kwargs["theme"] = theme
            result = planner.plan(**plan_kwargs)
        except PlannerError as exc:
            self._toast(f"pitch planning failed: {exc}"); return

        try:
            store = ContinuationStore(SETTINGS.paths.continuations_dir)
            store.create(
                goal=result.goal, planner="movie-pitch", planner_args=plan_kwargs,
                steps=result.steps, output_path=result.output_path, notes=result.notes,
            )
        except Exception as exc:  # noqa: BLE001
            self._toast(f"couldn't queue pitch continuation: {type(exc).__name__}: {exc}")
            return
        self._toast(f"queued {len(result.steps)} pitch(es) → {output} "
                   f"— drain the continuation to generate real content")

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#movie-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    MovieStudioScreen { align: center middle; background: $surface 60%; }
    #movie-modal {
        width: 76; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #movie-top { height: 3; margin-bottom: 1; }
    #movie-exit-btn { width: 1fr; margin-right: 1; }
    #movie-save-btn { width: 1fr; }
    #movie-title { text-style: bold; margin-bottom: 1; }
    #movie-status-header { height: 3; margin-bottom: 1; color: $text; }
    #movie-starter-ideas { margin-bottom: 1; }
    #movie-help { height: 3; color: $text-muted; margin-bottom: 1; }
    MovieStudioScreen Input, MovieStudioScreen Select { width: 100%; margin-bottom: 1; }
    MovieStudioScreen Label { color: $text-muted; }
    #movie-browse-sep { margin-top: 1; }
    .movie-carousel { height: 3; margin-bottom: 1; }
    .movie-carousel Button { width: 6; }
    .movie-carousel-label { width: 1fr; content-align: center middle; }
    #movie-actions { height: 3; margin-bottom: 1; }
    #movie-actions Button { width: 1fr; margin-right: 1; }
    #movie-gen-sep { margin-top: 1; }
    """


__all__ = ["MovieStudioScreen", "cycle_index"]
