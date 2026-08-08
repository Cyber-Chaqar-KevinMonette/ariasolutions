"""movie_pane.py — the ✦ movie split-pane: a quick-action + episode-
production command center living beside chat.

movie-focus-d (Kevin, 2026-07-28): "split the whole chat screen so left
side can be live chat and the right side can be whatever we have in the
movie side of the TUI" — then, immediately after: "You'll have to give me
commands and controls to master this video production system... one
panel. Contains everything we need." This is that one panel: the focused
project's quick actions (storyboard/clip/pitches, same real tools
Movie Studio's modal already calls) PLUS the episode-chaining render
session's controls (start/advance/pause/resume/assemble — the already-
proven-live `aria-movie-series` mechanism), through the shared
`movie_generation_actions` module so neither this pane nor the modal
duplicates the GPU-call wiring.

Deliberately a plain `Vertical`, not a `Screen`/`ModalScreen` — it lives
persistently inside `#main` (mirroring the cockpit's existing 5-pane
split, see cockpit/app.py), shown/hidden via the `movie-split` CSS class
on `#main`, never pushed/popped. The FULL editing form (define/edit/
remove/carousel/focus-switch) stays modal-only, reachable via the
"Full Movie Studio..." button here or /movies exactly as today — this
pane is scoped to quick actions + episode production, not a duplicate
of MovieStudioScreen's form.

Episode scope call (Kevin's own words were "may have to be," "possibly" —
hedged, not a hard spec): no full series/season picker UI. The pane
always operates on ONE "focused episode" (movie_series.get_episode_focus/
set_episode_focus), auto-creating the next season/episode under the
focused movie project on first use. Deeper multi-series/season management
is a natural next increment, not built here.
"""
from __future__ import annotations

import asyncio

from textual import work
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Rule, Static

__all__ = ["MoviePane"]

# Bounded batch size for the "Run" button — never an unbounded background
# loop from a single click, same discipline as everything else in this
# repo's long-running-work story.
RUN_BATCH_SIZE = 5

_TERMINAL_ADVANCE_OUTCOMES = (
    "episode_completed", "episode_exhausted", "episode_paused", "shot_poisoned_episode_paused",
    "episode_failed_health_check",
)

# Rough ETAs fed to bot_services.pause_for_production() so aria-bot's
# away-message can tell anyone who messages during production roughly
# when to expect her back — honest estimates, not hard guarantees, based
# on this hardware's proven ~1-3 min/clip generation time.
_ETA_MINUTES_SINGLE_CLIP = 3
_ETA_MINUTES_RUN_BATCH = RUN_BATCH_SIZE * 3

# Quick Fill (Kevin, 2026-07-28) — the exact prompt confirmed working live
# tonight (real recognizable red-cube storyboard/clip generation), so a
# click here proves the pipeline works with zero typing required. One box
# now (Kevin, 2026-07-28: "not 5 natural language chat boxes... combine
# the five into one chat box"), so one sample prompt.
QUICK_FILL_PROMPT = "a small red cube slowly rotating on a plain white background"

_COMMAND_HELP = (
    "didn't recognize that — try: focus <name> · new project · storyboard: <scene> · "
    "clip: <scene> · pitch <theme> · start: <beat> · add shot: <beat> · advance · run · "
    "pause · resume · assemble · verify · safety <strict|moderate|open> · "
    "auto series · stop auto series"
)


class MoviePane(VerticalScroll):
    """The one movie-production panel. Scrolls — two sections' worth of
    controls in one narrow column, mirroring MovieStudioScreen's own
    VerticalScroll."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Hardening pass (Kevin, 2026-07-28: "quality hardening and
        # assurance pass"). Real bug found: Textual's `@work(exclusive=True,
        # thread=True)` only cancels a worker's BOOKKEEPING — a plain Python
        # thread can't actually be killed, so a still-running thread keeps
        # executing to completion and its trailing call_from_thread toast
        # can land AFTER a newer action's, silently overwriting the visible
        # status with a stale result (confirmed empirically: two workers in
        # one exclusive group, the "cancelled" one's completion still fires
        # last). An explicit per-group busy guard — same pattern
        # capability_test_screen.py's own `_captest_running` flag already
        # uses — refuses a second click outright instead of racing.
        self._busy: set[str] = set()
        # Auto Series' own cancel flag (Kevin, 2026-07-28: "no human
        # required... use graceful sleep schedules") — the loop polls this
        # between clips; "Stop Auto Series" just flips it, same idiom as
        # the busy-guard above but for a mid-run cancel rather than a
        # refuse-to-start guard.
        self._auto_series_stop_flag = False

    def _try_start(self, group: str) -> bool:
        if group in self._busy:
            self._toast("still working on the previous action — wait for it to finish first")
            return False
        self._busy.add(group)
        return True

    def _finish(self, group: str) -> None:
        self._busy.discard(group)

    def compose(self):
        # movie-focus-d (Kevin, 2026-07-28): "give it the larger portion...
        # redesign it if we have to. Make it immersive and easy." Now that
        # this pane is the WIDE side (2fr vs chat's 1fr), the old one-long-
        # column layout wasted the extra width. Redesigned as: a full-width
        # header block (title/paths/live status, always visible without
        # scrolling past the controls) over a two-column body — quick
        # actions on the left, episode production on the right — with a
        # footer for the full modal. Every widget id is UNCHANGED from the
        # original single-column layout, only the surrounding containers
        # moved, so nothing that queries these ids needed to change.
        yield Static("", id="movie-pane-header")
        # movie-focus-d (Kevin, 2026-07-28): "it should show the file
        # location of all the series so I never forget." A permanent
        # anchor line — always visible regardless of focus state — plus
        # the focused project/episode's own concrete path shown in
        # #movie-pane-header / #movie-pane-episode-status below.
        yield Static("", id="movie-pane-storage-root")

        # Status moved up top (Kevin: "not sure if the buttons are doing
        # anything") — the ONE line that changes every time something
        # happens now sits where it's always visible, not buried below
        # two columns of controls.
        yield Static("", id="movie-pane-status")

        with Horizontal(id="movie-pane-columns"):
            with Vertical(id="movie-pane-quick-col", classes="movie-pane-col"):
                yield Static("Quick Actions", classes="movie-pane-col-title")
                yield Static(
                    "[dim]Type what you want, hit Go — or click a button below to use "
                    "what's typed for that specific action.[/dim]",
                    id="movie-pane-help",
                )

                # Kevin, 2026-07-28: "Not 5 natural language chat boxes... or
                # combine the five into one chat box that feels powerful and
                # natural and immersive, not confusing." This ONE box now
                # feeds every action below (focus/new project/storyboard/
                # clip/pitch/start/add shot) — Go does keyword dispatch
                # (mirrors the main chat input's own _handle_slash-then-
                # _dispatch_turn two-tier shape); each button below uses
                # whatever's typed here for that one specific action instead
                # of each having its own private input.
                yield Input(
                    value="", id="movie-pane-command",
                    placeholder="tell me what to do — e.g. 'clip: a cube spinning', "
                                "'focus my sci-fi project', 'auto series'",
                )
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Go", id="movie-pane-go", variant="primary")
                    yield Button("Quick Fill", id="movie-pane-quick-fill", variant="warning")

                # Kevin, 2026-07-28: "I need a way to add the project
                # focus... add a new project button and each movie project
                # can be named and numbered. Automatically." New Project
                # needs no typing at all (auto-names "Movie Project N");
                # Focus Project matches whatever's typed above against a
                # real project's title.
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("+ New Project", id="movie-pane-new-project")
                    yield Button("Focus Project", id="movie-pane-focus-project", variant="success")

                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Generate Storyboard", id="movie-pane-gen-storyboard", variant="primary")
                    yield Button("Generate Clip", id="movie-pane-gen-clip", variant="primary")
                yield Button("Draft Pitches", id="movie-pane-draft-pitches", variant="primary")

            yield Rule(orientation="vertical", id="movie-pane-col-divider")

            with Vertical(id="movie-pane-episode-col", classes="movie-pane-col"):
                yield Static("Episode Production", classes="movie-pane-col-title")
                yield Static("[dim]— episode production —[/dim]", id="movie-pane-episode-sep")
                yield Static("", id="movie-pane-episode-status")

                # Real bug found + fixed live (Kevin, 2026-07-28: "I clicked
                # run 5 clips... I see no obvious observables"): Start
                # Episode used to create an episode with ZERO shots, so
                # Advance/Run completed instantly with nothing to render.
                # Start Episode/Add Shot now read their beat from the ONE
                # command box above (Kevin: "combine the five into one chat
                # box") — empty is fine too, it falls back to the series
                # logline.
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Start Episode", id="movie-pane-start-episode", variant="success")
                    yield Button("Advance", id="movie-pane-advance", variant="primary")
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Add Shot", id="movie-pane-add-shot")
                    yield Button(f"Run ({RUN_BATCH_SIZE} clips)", id="movie-pane-run5", variant="primary")
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Pause", id="movie-pane-pause")
                    yield Button("Resume", id="movie-pane-resume")
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Assemble", id="movie-pane-assemble", variant="success")
                    # Kevin, 2026-07-29: "add a episode verify health and
                    # success auto checking feature." Runs automatically
                    # after every completion now, but this lets you
                    # re-check ANY episode on demand — including old ones
                    # from before this feature existed.
                    yield Button("Verify", id="movie-pane-verify")

                # Kevin, 2026-07-28: "Add a button in the studio panel for
                # auto project/auto series... no human required." Arms a
                # real, bounded AutoCrownStore session (the SAME timed,
                # tier-capped consent this app already uses for every other
                # unattended loop — never a separate ungated mechanism) and
                # then runs the whole design-and-render loop unattended
                # until that window ends, Stop is clicked, or a real
                # terminal state is reached.
                with Horizontal(classes="movie-pane-episode-row"):
                    yield Button("Auto Series", id="movie-pane-auto-series", variant="warning")
                    yield Button("Stop Auto Series", id="movie-pane-stop-auto-series", variant="error")

        with Horizontal(id="movie-pane-full-studio-row"):
            yield Button("Full Movie Studio...", id="movie-pane-full-studio")

    def on_mount(self) -> None:
        self.refresh_all()

    def refresh_all(self) -> None:
        self._refresh_storage_root()
        self._refresh_header()
        self._refresh_episode_status()

    # ── status readers (mirror movie_studio_screen.py's own reads) ─────────

    def _refresh_storage_root(self) -> None:
        """Kevin, 2026-07-28: 'it should show the file location of all
        the series so I never forget.' A permanent, always-on anchor:
        every movie project/series/episode lives under one root, shown
        here regardless of what's currently focused."""
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_series import list_all_series

            root = SETTINGS.paths.sandbox_dir / "movies"
            series = list_all_series(SETTINGS.paths.data_dir)
            lines = [f"[dim]all series live under:[/dim] {root}"]
            for s in series:
                lines.append(f"  [dim]•[/dim] {s.title}: {root / s.slug}")
            self.query_one("#movie-pane-storage-root", Static).update("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    def _focused_project_slug(self) -> str | None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_projects import get_focus
            return get_focus(SETTINGS.paths.data_dir).slug
        except Exception:  # noqa: BLE001
            return None

    def _refresh_header(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_assets import check_workspace_budget
            from sovereign_agent.movie_dev_xp import level_for_xp, progress_to_next, total_xp
            from sovereign_agent.movie_projects import get_focus, load_by_slug, movie_workspace_dir

            data_dir = SETTINGS.paths.data_dir
            focus = get_focus(data_dir)
            xp = total_xp(data_dir=data_dir)
            level = level_for_xp(xp)
            within, per_level = progress_to_next(xp)

            if focus.slug:
                proj = load_by_slug(focus.slug, data_dir)
                label = proj.title if proj else focus.slug
                workspace = movie_workspace_dir(focus.slug)
                try:
                    budget = check_workspace_budget(workspace)
                    storage = f" · {budget.used_mb}MB/{budget.budget_mb}MB"
                except Exception:  # noqa: BLE001
                    storage = ""
                path_line = f"\n[dim]files:[/dim] {workspace}"
                # Kevin, 2026-07-29: "add safety levels. Which can be
                # applied per series." Shown so it's never a hidden
                # setting — always visible which guardrail level is
                # actually active for whatever's focused right now.
                try:
                    from sovereign_agent.movie_series import load_series_by_slug
                    series = load_series_by_slug(focus.slug, data_dir)
                    safety = series.safety_level if series else "strict"
                except Exception:  # noqa: BLE001
                    safety = "strict"
                safety_line = f"\n[dim]safety:[/dim] {safety}"
            else:
                label = "(none — open Full Movie Studio to define one)"
                storage = ""
                path_line = ""
                safety_line = ""

            header = f"[b]{label}[/b]{storage} · Lv.{level} · XP {within}/{per_level}{safety_line}{path_line}"
            self.query_one("#movie-pane-header", Static).update(header)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_episode_status(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_episode_render import EpisodeStore
            from sovereign_agent.movie_series import get_episode_focus

            data_dir = SETTINGS.paths.data_dir
            focus = get_episode_focus(data_dir)
            if not focus.episode_id:
                self.query_one("#movie-pane-episode-status", Static).update(
                    "[dim]no episode yet — Start Episode to begin[/dim]"
                )
                return
            store = EpisodeStore(data_dir / "movie_episodes", SETTINGS.paths.sandbox_dir / "movies")
            try:
                ep = store.get(focus.episode_id)
            except Exception:  # noqa: BLE001
                self.query_one("#movie-pane-episode-status", Static).update(
                    f"[dim]{focus.episode_id}: could not load[/dim]"
                )
                return
            self.query_one("#movie-pane-episode-status", Static).update(
                f"[b]{ep.episode_id}[/b] · {ep.status} · {ep.progress_summary()} · "
                f"{ep.elapsed_seconds:.0f}s\n[dim]files:[/dim] {ep.work_dir}"
            )
        except Exception:  # noqa: BLE001
            pass

    def _toast(self, msg: str) -> None:
        # Kevin, 2026-07-28: full-contrast, not [dim] — the CSS already
        # makes #movie-pane-status bold/full-color; wrapping in [dim] here
        # would fight that same "make sure this is visibly changing" fix.
        try:
            self.query_one("#movie-pane-status", Static).update(msg)
        except Exception:  # noqa: BLE001
            pass

    # ── button dispatch ──────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Kevin, 2026-07-28: "not sure if the buttons are doing anything" —
        # every OTHER button in this cockpit flashes on click
        # (CommandButton.flash, 0.3s); these plain Buttons had no click
        # feedback at all. Same convention, applied here.
        event.button.add_class("flash")
        self.set_timer(0.3, lambda: event.button.remove_class("flash"))

        bid = event.button.id
        if bid == "movie-pane-go":
            self._dispatch_command(); return
        if bid == "movie-pane-auto-series":
            self._auto_series(); return
        if bid == "movie-pane-stop-auto-series":
            self._stop_auto_series(); return
        if bid == "movie-pane-new-project":
            self._new_project(); return
        if bid == "movie-pane-focus-project":
            self._focus_project(); return
        if bid == "movie-pane-quick-fill":
            self._quick_fill(); return
        if bid == "movie-pane-full-studio":
            self.app.action_movie_studio(); return
        if bid == "movie-pane-gen-storyboard":
            self._generate_storyboard(); return
        if bid == "movie-pane-gen-clip":
            self._generate_clip(); return
        if bid == "movie-pane-draft-pitches":
            self._draft_pitches(); return
        if bid == "movie-pane-start-episode":
            self._start_episode(); return
        if bid == "movie-pane-add-shot":
            self._add_shot(); return
        if bid == "movie-pane-advance":
            self._advance_episode(); return
        if bid == "movie-pane-run5":
            self._run_episode_batch(); return
        if bid == "movie-pane-pause":
            self._pause_episode(); return
        if bid == "movie-pane-resume":
            self._resume_episode(); return
        if bid == "movie-pane-assemble":
            self._assemble_episode(); return
        if bid == "movie-pane-verify":
            self._verify_episode(); return

    # ── quick actions ────────────────────────────────────────────────────

    def _new_project(self) -> None:
        """Kevin, 2026-07-28: 'add a new project button and each movie
        project can be named and numbered. Automatically.' No form, no
        typing — auto-names 'Movie Project N' (N = next free number,
        never collides with an existing title), saves it for real, and
        focuses it immediately."""
        if not self._try_start("moviepane-new-project"):
            return
        self._toast("creating new project…")
        self._new_project_worker()

    @work(thread=True, exclusive=True, group="moviepane-new-project")
    def _new_project_worker(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_projects import MovieProject, list_all, save, set_focus, slugify
        try:
            title = ""
            try:
                data_dir = SETTINGS.paths.data_dir
                existing_titles = {p.title for p in list_all(data_dir)}
                n = len(existing_titles) + 1
                title = f"Movie Project {n}"
                while title in existing_titles:
                    n += 1
                    title = f"Movie Project {n}"
                save(MovieProject(title=title), data_dir)
                set_focus(slugify(title), "created from the movie pane", data_dir)
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"new project failed: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, f"created + focused: {title}")
            self.app.call_from_thread(self._refresh_header)
        finally:
            self._finish("moviepane-new-project")

    def _command_text(self) -> str:
        return self.query_one("#movie-pane-command", Input).value.strip()

    def _focus_project(self, query: str | None = None) -> None:
        """Kevin, 2026-07-28: 'I need a way to add the project focus. Add
        a way into the menu please.' Now text-driven (Kevin: 'combine the
        five into one chat box') — matches whatever's typed against a
        real project's title (case-insensitive substring) instead of a
        dropdown. A canned reason (not a typed one) keeps this quick, same
        trade-off run_start_episode already made for episode focus; the
        full modal's carousel still supports a real typed reason for
        anyone who wants that audit detail."""
        query = query if query is not None else self._command_text()
        if not query:
            self._toast("type (part of) a project's title first, then Focus Project"); return
        if not self._try_start("moviepane-focus-project"):
            return
        self._toast("focusing project…")
        self._focus_project_worker(query)

    @work(thread=True, exclusive=True, group="moviepane-focus-project")
    def _focus_project_worker(self, query: str) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_projects import list_all, set_focus, slugify
        try:
            try:
                data_dir = SETTINGS.paths.data_dir
                matches = [p for p in list_all(data_dir) if query.lower() in p.title.lower()]
                if not matches:
                    titles = ", ".join(p.title for p in list_all(data_dir)) or "(none yet)"
                    self.app.call_from_thread(
                        self._toast, f"no project title matches {query!r} — have: {titles}")
                    return
                if len(matches) > 1:
                    titles = ", ".join(p.title for p in matches)
                    self.app.call_from_thread(
                        self._toast, f"{query!r} matches more than one: {titles} — be more specific")
                    return
                title = matches[0].title
                set_focus(slugify(title), "focused from the movie pane", data_dir)
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"focus failed: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, f"focused: {title}")
            self.app.call_from_thread(self._refresh_header)
        finally:
            self._finish("moviepane-focus-project")

    def _set_safety_level(self, level: str | None = None) -> None:
        """Kevin, 2026-07-29: 'add movie production guardrails... add
        safety levels. Which can be applied per series.'"""
        slug = self._focused_project_slug()
        if not slug:
            self._toast("no project focused — open Full Movie Studio to define/focus one"); return
        level = (level or self._command_text()).strip().lower()
        if not level:
            self._toast("type a level first — strict, moderate, or open"); return
        if not self._try_start("moviepane-safety-level"):
            return
        self._toast("setting safety level…")
        self._set_safety_level_worker(slug, level)

    @work(thread=True, exclusive=True, group="moviepane-safety-level")
    def _set_safety_level_worker(self, project_slug: str, level: str) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_content_safety import SAFETY_LEVELS
        from sovereign_agent.movie_projects import load_by_slug
        from sovereign_agent.movie_series import Series, load_series_by_slug, save_series, set_safety_level
        try:
            try:
                if level not in SAFETY_LEVELS:
                    self.app.call_from_thread(
                        self._toast, f"unknown safety level {level!r} — use: {', '.join(SAFETY_LEVELS)}")
                    return
                data_dir = SETTINGS.paths.data_dir
                if load_series_by_slug(project_slug, data_dir) is None:
                    project = load_by_slug(project_slug, data_dir)
                    if project is None:
                        self.app.call_from_thread(self._toast, f"no project or series with slug {project_slug!r}")
                        return
                    save_series(Series(
                        title=project.title, logline=project.logline,
                        genre=project.genre, style=project.style,
                    ), data_dir)
                set_safety_level(project_slug, level, data_dir)
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"safety level failed: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, f"safety level set to {level!r}")
            self.app.call_from_thread(self._refresh_header)
        finally:
            self._finish("moviepane-safety-level")

    def _quick_fill(self) -> None:
        """Fills the one command box with the exact sample text confirmed
        working live tonight (real storyboard/clip generation) — click
        Quick Fill, then Generate Clip/Storyboard to prove the pipeline
        works with zero typing required."""
        self.query_one("#movie-pane-command", Input).value = QUICK_FILL_PROMPT
        self._toast("filled in a sample prompt — click Generate Clip/Storyboard to test")

    def _generate_storyboard(self, prompt: str | None = None) -> None:
        slug = self._focused_project_slug()
        if not slug:
            self._toast("no project focused — open Full Movie Studio to define/focus one"); return
        prompt = prompt if prompt is not None else self._command_text()
        if not prompt:
            self._toast("storyboard needs a prompt — describe the shot/scene"); return
        if not self._try_start("moviepane-storyboard"):
            return
        self._toast("generating storyboard — this can take a while…")
        self._storyboard_worker(slug, prompt)

    @work(thread=True, exclusive=True, group="moviepane-storyboard")
    def _storyboard_worker(self, slug: str, prompt: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_generate_storyboard

        try:
            try:
                message = asyncio.run(run_generate_storyboard(slug, prompt, on_wait=self._make_on_wait()))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"storyboard error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
            self.app.call_from_thread(self._refresh_header)
        finally:
            self._finish("moviepane-storyboard")

    def _generate_clip(self, prompt: str | None = None) -> None:
        slug = self._focused_project_slug()
        if not slug:
            self._toast("no project focused — open Full Movie Studio to define/focus one"); return
        prompt = prompt if prompt is not None else self._command_text()
        if not prompt:
            self._toast("clip needs a prompt — describe the shot/scene"); return
        if not self._try_start("moviepane-clip"):
            return
        self._toast("generating clip — real, local, slow (~1-3 min on this hardware)…")
        self._clip_worker(slug, prompt)

    def _make_on_wait(self):
        def _on_wait(available_mb, elapsed) -> None:
            self.app.call_from_thread(
                self._toast,
                f"please wait — movie studio vision model is loading, "
                f"waiting for system RAM to clear ({elapsed:.0f}s, {available_mb}MB available)…",
            )
        return _on_wait

    def _make_on_step(self, label: str):
        """Kevin, 2026-07-28: 'can we watch the movies generate live???' —
        real per-denoising-step progress (diffusers' own
        callback_on_step_end, confirmed real, not a fake timer), pushed
        to the status line as it happens instead of one static "please
        wait" for the whole 60-120s generation."""
        def _on_step(step: int, total: int) -> None:
            self.app.call_from_thread(self._toast, f"{label} — step {step}/{total}…")
        return _on_step

    def _pause_bots_for_production(self, *, eta_minutes: float | None = None) -> bool:
        """Kevin, 2026-07-29: 'make sure the bots automatically pause
        while episodes are being produced... to prevent memory leaks.'
        Called ONCE per production session (one clip, one Advance, or
        one whole Run/Auto Series batch) — never per clip inside a loop,
        which would just bounce the Discord gateway connection
        constantly. Returns was_active so the matching resume call knows
        whether it's actually responsible for turning anything back on.
        `eta_minutes` feeds the production flag aria-bot's own message
        handler reads to tell anyone who messages/pings during this
        window roughly when she'll be back (Kevin, same night: "leave an
        ETA of how long until they should be until they are back
        online")."""
        from sovereign_agent import bot_services
        try:
            was_active, receipt = bot_services.pause_for_production(eta_minutes=eta_minutes)
            if was_active:
                self.app.call_from_thread(self._toast, f"pausing bots for production — {receipt}")
            return was_active
        except Exception:  # noqa: BLE001 — a bot-pause failure must never block real generation
            return False

    def _resume_bots_after_production(self, was_active: bool) -> None:
        from sovereign_agent import bot_services
        try:
            bot_services.resume_after_production(was_active)
        except Exception:  # noqa: BLE001
            pass

    @work(thread=True, exclusive=True, group="moviepane-clip")
    def _clip_worker(self, slug: str, prompt: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_generate_clip

        was_active = self._pause_bots_for_production(eta_minutes=_ETA_MINUTES_SINGLE_CLIP)
        try:
            try:
                message = asyncio.run(run_generate_clip(
                    slug, prompt, on_wait=self._make_on_wait(), on_step=self._make_on_step("generating clip"),
                ))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"clip error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
            self.app.call_from_thread(self._refresh_header)
        finally:
            self._resume_bots_after_production(was_active)
            self._finish("moviepane-clip")

    def _draft_pitches(self, theme: str | None = None) -> None:
        theme = theme if theme is not None else self._command_text()
        if not self._try_start("moviepane-pitches"):
            return
        self._toast("drafting pitches…")
        self._pitches_worker(theme)

    @work(thread=True, exclusive=True, group="moviepane-pitches")
    def _pitches_worker(self, theme: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_draft_pitches
        try:
            try:
                message = asyncio.run(run_draft_pitches(theme))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"pitch error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
        finally:
            self._finish("moviepane-pitches")

    # ── episode production ───────────────────────────────────────────────
    #
    # All six episode actions share ONE busy key ("moviepane-episode"),
    # same as their shared @work group — they all mutate the SAME
    # episode's state, so they must be mutually exclusive with each other,
    # not just with themselves.

    def _focused_episode_id(self) -> str | None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.movie_series import get_episode_focus
            return get_episode_focus(SETTINGS.paths.data_dir).episode_id
        except Exception:  # noqa: BLE001
            return None

    def _start_episode(self, beat: str | None = None) -> None:
        slug = self._focused_project_slug()
        if not slug:
            self._toast("no project focused — open Full Movie Studio to define/focus one"); return
        beat = beat if beat is not None else self._command_text()
        if not self._try_start("moviepane-episode"):
            return
        self._toast("starting episode…")
        self._start_episode_worker(slug, beat)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _start_episode_worker(self, slug: str, beat: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_start_episode
        try:
            try:
                message = asyncio.run(run_start_episode(slug, beat=beat))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"start episode error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
            self.app.call_from_thread(self._refresh_episode_status)
        finally:
            self._finish("moviepane-episode")

    def _add_shot(self, beat: str | None = None) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused — Start Episode first"); return
        beat = beat if beat is not None else self._command_text()
        if not beat:
            self._toast("add shot needs a beat — describe what happens in this shot"); return
        if not self._try_start("moviepane-episode"):
            return
        self._toast("queuing shot…")
        self._add_shot_worker(episode_id, beat)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _add_shot_worker(self, episode_id: str, beat: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_add_shot
        try:
            try:
                message = asyncio.run(run_add_shot(episode_id, beat))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"add shot error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
            self.app.call_from_thread(self._refresh_episode_status)
        finally:
            self._finish("moviepane-episode")

    def _advance_episode(self) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused — Start Episode first"); return
        if not self._try_start("moviepane-episode"):
            return
        self._toast("advancing one clip…")
        self._advance_worker(episode_id)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _advance_worker(self, episode_id: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_advance_episode

        was_active = self._pause_bots_for_production(eta_minutes=_ETA_MINUTES_SINGLE_CLIP)
        try:
            try:
                message = asyncio.run(run_advance_episode(
                    episode_id, on_wait=self._make_on_wait(), on_step=self._make_on_step("advancing"),
                ))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"advance error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
            self.app.call_from_thread(self._refresh_episode_status)
        finally:
            self._resume_bots_after_production(was_active)
            self._finish("moviepane-episode")

    def _run_episode_batch(self) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused — Start Episode first"); return
        if not self._try_start("moviepane-episode"):
            return
        self._toast(f"running up to {RUN_BATCH_SIZE} clips…")
        self._run_batch_worker(episode_id)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _run_batch_worker(self, episode_id: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_advance_episode

        was_active = self._pause_bots_for_production(eta_minutes=_ETA_MINUTES_RUN_BATCH)
        try:
            last_message = ""
            for i in range(RUN_BATCH_SIZE):
                on_step = self._make_on_step(f"clip {i + 1}/{RUN_BATCH_SIZE}")
                try:
                    last_message = asyncio.run(run_advance_episode(
                        episode_id, on_wait=self._make_on_wait(), on_step=on_step,
                    ))
                except Exception as exc:  # noqa: BLE001
                    last_message = f"advance error: {type(exc).__name__}: {exc}"
                    break
                self.app.call_from_thread(self._refresh_episode_status)
                if any(outcome in last_message for outcome in _TERMINAL_ADVANCE_OUTCOMES):
                    break
            self.app.call_from_thread(self._toast, last_message)
        finally:
            self._resume_bots_after_production(was_active)
            self._finish("moviepane-episode")

    def _pause_episode(self) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused"); return
        if not self._try_start("moviepane-episode"):
            return
        self._episode_lifecycle_worker("pause", episode_id)

    def _resume_episode(self) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused"); return
        if not self._try_start("moviepane-episode"):
            return
        self._episode_lifecycle_worker("resume", episode_id)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _episode_lifecycle_worker(self, verb: str, episode_id: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import (
            run_pause_episode, run_resume_episode,
        )
        fn = run_pause_episode if verb == "pause" else run_resume_episode
        try:
            try:
                message = asyncio.run(fn(episode_id))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"{verb} error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
            self.app.call_from_thread(self._refresh_episode_status)
        finally:
            self._finish("moviepane-episode")

    def _verify_episode(self) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused"); return
        if not self._try_start("moviepane-episode"):
            return
        self._toast("verifying…")
        self._verify_worker(episode_id)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _verify_worker(self, episode_id: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_verify_episode_health
        try:
            try:
                message = asyncio.run(run_verify_episode_health(episode_id))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"verify error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
        finally:
            self._finish("moviepane-episode")

    def _assemble_episode(self) -> None:
        episode_id = self._focused_episode_id()
        if not episode_id:
            self._toast("no episode focused"); return
        if not self._try_start("moviepane-episode"):
            return
        self._toast("assembling…")
        self._assemble_worker(episode_id)

    @work(thread=True, exclusive=True, group="moviepane-episode")
    def _assemble_worker(self, episode_id: str) -> None:
        from sovereign_agent.cockpit.movie_generation_actions import run_assemble_episode
        try:
            try:
                message = asyncio.run(run_assemble_episode(episode_id))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"assemble error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, message)
        finally:
            self._finish("moviepane-episode")

    # ── Auto Series ──────────────────────────────────────────────────────

    def _auto_series(self) -> None:
        """Kevin, 2026-07-28: "Add a button in the studio panel for auto
        project/auto series... no human required." One click: arms a
        real, bounded AutoCrownStore session if none is already active
        (the SAME timed, tier-capped consent this app already uses for
        every other unattended loop — never a separate ungated
        mechanism), then runs the whole design-and-render loop
        unattended."""
        if not self._try_start("moviepane-auto-series"):
            return
        self._auto_series_stop_flag = False
        self._toast("starting Auto Series…")
        self._auto_series_worker()

    def _stop_auto_series(self) -> None:
        if "moviepane-auto-series" not in self._busy:
            self._toast("Auto Series isn't running"); return
        self._auto_series_stop_flag = True
        self._toast("stopping Auto Series — finishing the current step first…")

    @work(thread=True, exclusive=True, group="moviepane-auto-series")
    def _auto_series_worker(self) -> None:
        import uuid

        from sovereign_agent.auto_crown import TRUST_TIER_MAX_HOURS, get_auto_crown_store
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.movie_auto_series_runner import run_auto_series
        try:
            store = get_auto_crown_store()
            try:
                session = store.status()
                if session is None or session.status != "active" or store.is_expired():
                    max_tier = store.get_max_trust_tier()
                    hours = min(2.0, TRUST_TIER_MAX_HOURS.get(max_tier, 1.0))
                    store.start(hours, max_tier, "Auto Series from the movie pane",
                               f"auto-series-{uuid.uuid4().hex[:8]}")
                    self.app.call_from_thread(
                        self._toast, f"armed Auto ({hours:.1f}h) — designing + rendering…")
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"could not arm Auto: {type(exc).__name__}: {exc}")
                return
            try:
                result = asyncio.run(run_auto_series(
                    data_dir=SETTINGS.paths.data_dir, sandbox_dir=SETTINGS.paths.sandbox_dir,
                    on_status=lambda msg: self.app.call_from_thread(self._toast, msg),
                    should_stop=lambda: self._auto_series_stop_flag,
                    auto_crown_store=store,
                ))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._toast, f"Auto Series error: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._toast, result)
            self.app.call_from_thread(self._refresh_header)
            self.app.call_from_thread(self._refresh_episode_status)
        finally:
            self._finish("moviepane-auto-series")

    # ── one command box: keyword dispatch ───────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "movie-pane-command":
            self._dispatch_command()

    def _dispatch_command(self) -> None:
        """Kevin, 2026-07-28: "Not 5 natural language chat boxes... combine
        the five into one chat box that feels powerful and natural and
        immersive, not confusing" — then later "we want full natural
        language autonomy." Mirrors the main chat input's own two-tier
        shape (_handle_slash's keyword dispatch, same idea as
        cockpit/app.py): deterministic, zero-cost keyword parsing first
        for every real action this pane has; anything that doesn't match
        falls through to a real orchestrator call that classifies the
        free-form text (movie_series_auto.classify_command) and then
        dispatches through these SAME action methods — the model
        understands what you mean, but it never calls a tool directly
        from this path (see _act_on_classified_command)."""
        text = self._command_text()
        if not text:
            self._toast("type something first — e.g. 'clip: a cube spinning', "
                        "'focus my project', 'auto series'")
            return
        lower = text.lower()

        def _after(*prefixes: str) -> str:
            for p in prefixes:
                if lower.startswith(p):
                    return text[len(p):].strip(" :")
            return text

        if lower.startswith("focus"):
            self._focus_project(_after("focus")); return
        if lower.startswith("new project") or lower == "new":
            self._new_project(); return
        if lower.startswith("storyboard") or lower.startswith("board"):
            self._generate_storyboard(_after("storyboard", "board")); return
        if lower.startswith("clip"):
            self._generate_clip(_after("clip")); return
        if lower.startswith("pitch"):
            self._draft_pitches(_after("pitch")); return
        if lower.startswith("add shot"):
            self._add_shot(_after("add shot")); return
        if lower.startswith("start"):
            self._start_episode(_after("start episode", "start")); return
        if lower == "advance":
            self._advance_episode(); return
        if lower.startswith("run"):
            self._run_episode_batch(); return
        if lower == "pause":
            self._pause_episode(); return
        if lower == "resume":
            self._resume_episode(); return
        if lower == "assemble":
            self._assemble_episode(); return
        if lower == "verify":
            self._verify_episode(); return
        if lower.startswith("safety"):
            self._set_safety_level(_after("safety")); return
        if lower in ("stop", "stop auto series", "stop auto"):
            self._stop_auto_series(); return
        if lower in ("auto series", "auto", "auto-series"):
            self._auto_series(); return

        # No keyword matched — full natural-language fallback.
        if not self._try_start("moviepane-command-fallback"):
            return
        self._toast("thinking about what you mean…")
        self._command_fallback_worker(text)

    @work(thread=True, exclusive=True, group="moviepane-command-fallback")
    def _command_fallback_worker(self, text: str) -> None:
        from sovereign_agent.movie_series_auto import classify_command
        try:
            try:
                action, argument = asyncio.run(classify_command(text))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(
                    self._toast, f"couldn't understand that: {type(exc).__name__}: {exc}")
                return
            self.app.call_from_thread(self._act_on_classified_command, action, argument)
        finally:
            self._finish("moviepane-command-fallback")

    def _act_on_classified_command(self, action: str, argument: str) -> None:
        """Runs on the main thread — dispatches to the SAME action methods
        the keyword table uses. This is the whole point of the design:
        the model only ever picks a name off a fixed, already-audited
        list; it never gets to invoke anything the keyword path couldn't
        already reach."""
        no_arg = {
            "new_project": self._new_project,
            "advance": self._advance_episode,
            "run": self._run_episode_batch,
            "pause": self._pause_episode,
            "resume": self._resume_episode,
            "assemble": self._assemble_episode,
            "verify": self._verify_episode,
            "auto_series": self._auto_series,
            "stop_auto_series": self._stop_auto_series,
        }
        needs_arg = {
            "focus": self._focus_project,
            "storyboard": self._generate_storyboard,
            "clip": self._generate_clip,
            "pitch": self._draft_pitches,
            "add_shot": self._add_shot,
            "start_episode": self._start_episode,
            "safety": self._set_safety_level,
        }
        if action in no_arg:
            no_arg[action](); return
        if action in needs_arg:
            needs_arg[action](argument); return
        self._toast(_COMMAND_HELP)

    # Base state is hidden — #main.movie-split (cockpit/app.py) is what
    # reveals + widths this pane, same "container-class toggles a sibling
    # pane" pattern obs-focus/chat-top already use for #chat-pane. Nothing
    # here assumes it's visible by default.
    #
    # Real bug found live (Kevin, 2026-07-28: "the middle window is all
    # black... totally blank, no border, no title"): Textual auto-scopes a
    # widget's own DEFAULT_CSS, so an ID selector matching the widget's OWN
    # id inside its OWN class's DEFAULT_CSS does NOT match itself (it scopes
    # to DESCENDANTS only) — confirmed via a minimal isolated repro:
    # `#test-pane { background: red }` inside TestPane(VerticalScroll)'s own
    # DEFAULT_CSS silently never applies, while `TestPane { background: red }`
    # (a type selector) does. `#movie-pane { background: $surface }` was
    # therefore silently a no-op, leaving the pane's background fully
    # transparent (alpha=0) — which several terminals paint as solid black.
    # The app.py-side `#main.movie-split #movie-pane { ... }` override
    # (defined on CockpitApp, a DIFFERENT class, not auto-scoped to this one)
    # was never affected — only this widget's own self-styling was broken.
    DEFAULT_CSS = """
    MoviePane {
        display: none;
        border-left: solid $primary;
        padding: 0 1;
        background: $surface;
    }
    #movie-pane-header { height: auto; text-style: bold; margin-bottom: 1; }
    #movie-pane-storage-root { height: auto; color: $text-muted; margin-bottom: 1; }
    /* Kevin, 2026-07-28: "not sure if the buttons are doing anything" —
       full-contrast $text (not $text-muted), bordered, and moved to the
       TOP of the pane (above both columns) so a status update is always
       visible without scrolling past a column of controls to see it. */
    #movie-pane-status {
        height: auto; min-height: 3; color: $text; text-style: bold;
        margin-bottom: 1; padding: 0 1; border: round $primary;
    }

    /* movie-focus-d redesign (Kevin, 2026-07-28): "give it the larger
       portion... redesign it if we have to, make it immersive and easy."
       Two columns side by side now that this pane is the WIDE side —
       quick single-shot actions on the left, the episode-chaining
       production controls on the right, a divider between them mirroring
       the same Rule style the cockpit's other panes already use. */
    #movie-pane-columns { height: auto; margin-bottom: 1; }
    .movie-pane-col { width: 1fr; height: auto; padding: 0 1; }
    #movie-pane-col-divider { width: 1; margin: 0 1; }
    .movie-pane-col-title {
        text-style: bold; color: $accent; margin-bottom: 1;
        border-bottom: solid $primary;
    }
    #movie-pane-help { margin-bottom: 1; }
    MoviePane Input { width: 100%; margin-bottom: 1; }
    MoviePane Button { width: 100%; margin-bottom: 1; }
    /* Same 0.3s click-feedback convention as CommandButton.flash elsewhere
       in this cockpit — every button here now gets it (see on_button_pressed). */
    MoviePane Button.flash { border: round $success; background: $success 20%; color: $success; }
    #movie-pane-full-studio-row { margin-bottom: 1; }
    #movie-pane-episode-sep { margin-top: 0; color: $text-muted; }
    #movie-pane-episode-status { height: auto; color: $text; margin-bottom: 1; }
    .movie-pane-episode-row { height: 3; margin-bottom: 1; }
    .movie-pane-episode-row Button { width: 1fr; margin-right: 1; }
    """
