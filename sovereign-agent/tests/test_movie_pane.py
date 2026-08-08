"""Tests for movie_pane.py — the ✦ movie split-pane command center.

Direct Button.Pressed dispatch (not pilot.click) throughout, same reason
as test_movie_focus_toggle_buttons.py: the pane sits past the default
test-terminal's visible width once #main.movie-split is active."""
from __future__ import annotations

import pytest
from textual.widgets import Button, Input

import sovereign_agent.bot_services as bot_services_mod
from sovereign_agent.movie_projects import MovieProject, save as save_project, set_focus


@pytest.fixture(autouse=True)
def _never_touch_real_systemctl(monkeypatch):
    """The clip/advance/run-batch workers all pause/resume real bot
    services around generation now (Kevin, 2026-07-29: "make sure the
    bots automatically pause while episodes are being produced"). Must
    never hit real systemctl during a test."""
    monkeypatch.setattr(bot_services_mod, "pause_for_production",
                        lambda **kw: (False, "mocked — no real systemctl in tests"))
    monkeypatch.setattr(bot_services_mod, "resume_after_production",
                        lambda was_active, **kw: "mocked — no real systemctl in tests")


async def _open_pane(pilot):
    app = pilot.app
    btn = app.query_one("#movie-toggle-btn", Button)
    app.on_button_pressed(Button.Pressed(btn))
    await pilot.pause()
    return app


# ── busy-guard hardening (Kevin, 2026-07-28: "quality hardening and
# assurance pass") ──────────────────────────────────────────────────────
#
# Real bug found: Textual's @work(exclusive=True, thread=True) only
# cancels a worker's BOOKKEEPING — a plain Python thread can't actually be
# killed, so a still-running thread keeps executing to completion and its
# trailing call_from_thread toast can land AFTER a newer action's,
# silently overwriting the visible status with a stale result (confirmed
# empirically with an isolated Textual repro). These tests prove the
# explicit busy-guard (_try_start/_finish) actually refuses a second
# action instead of racing — same "call twice, no await between" idiom
# test_capability_test_cockpit.py's own double-click guard test uses.


@pytest.mark.asyncio
async def test_second_advance_click_while_busy_is_refused_not_raced(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from sovereign_agent.movie_series import set_episode_focus
    from sovereign_agent.config import SETTINGS

    set_episode_focus("ep-busytest-s01-e01-abc1234", "testing busy guard", SETTINGS.paths.data_dir)

    calls = []
    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        monkeypatch.setattr(pane, "_advance_worker", lambda episode_id: calls.append(episode_id))

        pane._advance_episode()
        pane._advance_episode()   # immediately again — no yield in between
        assert len(calls) == 1, "a second advance while busy must not start a second worker"


@pytest.mark.asyncio
async def test_pause_refused_while_advance_is_busy_shared_episode_key(monkeypatch):
    """The six episode actions share ONE busy key on purpose — they all
    mutate the SAME episode's state. Confirms cross-action exclusion, not
    just same-button double-clicks."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from sovereign_agent.movie_series import set_episode_focus
    from sovereign_agent.config import SETTINGS

    set_episode_focus("ep-busytest2-s01-e01-abc1234", "testing busy guard", SETTINGS.paths.data_dir)

    advance_calls = []
    pause_calls = []
    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        monkeypatch.setattr(pane, "_advance_worker", lambda episode_id: advance_calls.append(episode_id))
        monkeypatch.setattr(pane, "_episode_lifecycle_worker",
                           lambda verb, episode_id: pause_calls.append((verb, episode_id)))

        pane._advance_episode()   # marks "moviepane-episode" busy, never releases (worker replaced)
        pane._pause_episode()     # must be refused — same busy key, different button
        assert len(advance_calls) == 1
        assert len(pause_calls) == 0, "pause must be refused while advance holds the shared episode busy key"


@pytest.mark.asyncio
async def test_finish_releases_the_busy_key_so_a_later_call_succeeds():
    """The guard must not permanently wedge — once a worker's finally
    block runs, the SAME action must be clickable again."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)

        assert pane._try_start("moviepane-episode") is True
        assert pane._try_start("moviepane-episode") is False   # busy
        pane._finish("moviepane-episode")
        assert pane._try_start("moviepane-episode") is True   # released, works again


@pytest.mark.asyncio
async def test_toggling_reveals_movie_pane_with_focused_project_header():
    # SETTINGS.paths is a frozen dataclass (can't monkeypatch a field on
    # it) — same reason test_movie_studio_screen.py's own tests save
    # directly into SETTINGS.paths.data_dir with a uniquely-named project
    # rather than isolating via tmp_path.
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="Neon Skyline Pane Test"), SETTINGS.paths.data_dir)
    set_focus("neon-skyline-pane-test", "testing the pane", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        header_text = str(pane.query_one("#movie-pane-header", Static).render())
        assert "Neon Skyline Pane Test" in header_text
        assert "files:" in header_text   # movie-focus-d: the project's real workspace path


@pytest.mark.asyncio
async def test_quick_fill_populates_the_command_box_and_flashes():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane, QUICK_FILL_PROMPT

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        assert pane.query_one("#movie-pane-command", Input).value == ""

        btn = pane.query_one("#movie-pane-quick-fill", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        # everything on_button_pressed does (flash class + Quick Fill's
        # input assignment) is synchronous — check immediately, before
        # any pause lets the 0.3s flash-removal timer fire.
        assert "flash" in btn.classes
        assert pane.query_one("#movie-pane-command", Input).value == QUICK_FILL_PROMPT

        await pilot.pause(0.5)
        assert "flash" not in btn.classes   # confirms the removal timer really does fire


@pytest.mark.asyncio
async def test_storage_root_lists_every_series_file_location():
    """Kevin, 2026-07-28: 'it should show the file location of all the
    series so I never forget.' A permanent anchor, independent of what's
    currently focused."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import Series, save_series

    save_series(Series(title="Storage Root Test Alpha"), SETTINGS.paths.data_dir)
    save_series(Series(title="Storage Root Test Beta"), SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        text = str(pane.query_one("#movie-pane-storage-root", Static).render())
        assert "all series live under" in text
        assert "Storage Root Test Alpha" in text
        assert "Storage Root Test Beta" in text
        assert str(SETTINGS.paths.sandbox_dir / "movies") in text


@pytest.mark.asyncio
async def test_episode_status_shows_its_real_work_dir(monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_episode_render import EpisodeStore
    from sovereign_agent.movie_series import set_episode_focus

    store = EpisodeStore(SETTINGS.paths.data_dir / "movie_episodes", SETTINGS.paths.sandbox_dir / "movies")
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="PathTestEp")
    set_episode_focus(ep.episode_id, "testing path display", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        text = str(pane.query_one("#movie-pane-episode-status", Static).render())
        assert ep.work_dir in text


@pytest.mark.asyncio
async def test_generate_storyboard_without_project_focused_is_refused():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-gen-storyboard", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "no project focused" in str(pane.query_one("#movie-pane-status", Static).render())


@pytest.mark.asyncio
async def test_generate_clip_calls_the_shared_action(monkeypatch):
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="ClipFilm Pane Test"), SETTINGS.paths.data_dir)
    set_focus("clipfilm-pane-test", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions

    async def fake_run_generate_clip(slug, prompt, *, on_wait=None, on_step=None, data_dir=None):
        return "clip generated → /fake/clip.mp4"
    monkeypatch.setattr(actions, "run_generate_clip", fake_run_generate_clip)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "a red cube"
        btn = pane.query_one("#movie-pane-gen-clip", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "generated" in text:
                break
        assert "generated" in text


@pytest.mark.asyncio
async def test_generate_clip_pauses_and_resumes_bots_around_generation(monkeypatch):
    """Kevin, 2026-07-29: 'make sure the bots automatically pause while
    episodes are being produced... and resume when episodes are not
    being produced.' Confirms the wiring actually fires (not just that
    it's safely mocked) — pause before generation, resume after, with
    the single-clip ETA."""
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="PauseFilm Pane Test"), SETTINGS.paths.data_dir)
    set_focus("pausefilm-pane-test", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions
    from sovereign_agent.cockpit.movie_pane import _ETA_MINUTES_SINGLE_CLIP

    async def fake_run_generate_clip(slug, prompt, *, on_wait=None, on_step=None, data_dir=None):
        return "clip generated → /fake/clip.mp4"
    monkeypatch.setattr(actions, "run_generate_clip", fake_run_generate_clip)

    pause_calls = []
    resume_calls = []
    monkeypatch.setattr(bot_services_mod, "pause_for_production",
                        lambda **kw: (pause_calls.append(kw) or (True, "▪ aria-duty STOPPED")))
    monkeypatch.setattr(bot_services_mod, "resume_after_production",
                        lambda was_active, **kw: resume_calls.append(was_active) or "resumed")

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "a red cube"
        btn = pane.query_one("#movie-pane-gen-clip", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "generated" in text:
                break
        assert pause_calls == [{"eta_minutes": _ETA_MINUTES_SINGLE_CLIP}]
        assert resume_calls == [True]


@pytest.mark.asyncio
async def test_generate_clip_shows_real_live_step_progress(monkeypatch):
    """Kevin, 2026-07-28: 'can we watch the movies generate live???' —
    confirms a real diffusers-style step callback actually updates the
    visible status line mid-generation, not just at the end."""
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="LiveProgressFilm"), SETTINGS.paths.data_dir)
    set_focus("liveprogressfilm", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions

    async def fake_run_generate_clip(slug, prompt, *, on_wait=None, on_step=None, data_dir=None):
        if on_step is not None:
            on_step(7, 30)
        return "clip generated → /fake/clip.mp4"
    monkeypatch.setattr(actions, "run_generate_clip", fake_run_generate_clip)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)

        # both the step-progress update and the final message post via
        # call_from_thread microseconds apart in this fake — polling the
        # rendered widget can race past the intermediate state entirely.
        # Recording every _toast call instead proves the wiring reached
        # it at all, regardless of exact timing.
        seen_messages = []
        original_toast = pane._toast
        def _recording_toast(msg):
            seen_messages.append(msg)
            original_toast(msg)
        pane._toast = _recording_toast

        pane.query_one("#movie-pane-command", Input).value = "a red cube"
        btn = pane.query_one("#movie-pane-gen-clip", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            if any("generated" in m for m in seen_messages):
                break
        assert any("step 7/30" in m for m in seen_messages)


@pytest.mark.asyncio
async def test_start_episode_without_project_focused_is_refused():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-start-episode", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "no project focused" in str(pane.query_one("#movie-pane-status", Static).render())


@pytest.mark.asyncio
async def test_advance_without_episode_focused_is_refused():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-advance", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "no episode focused" in str(pane.query_one("#movie-pane-status", Static).render())


@pytest.mark.asyncio
async def test_start_episode_calls_shared_action_and_refreshes_status(monkeypatch):
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="EpFilm Pane Test"), SETTINGS.paths.data_dir)
    set_focus("epfilm-pane-test", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions

    async def fake_run_start_episode(series_slug, *, title="", beat="", on_wait=None, data_dir=None, sandbox_dir=None):
        return "started episode ep-epfilm-s01-e01-abc1234 — ready to Advance"
    monkeypatch.setattr(actions, "run_start_episode", fake_run_start_episode)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-start-episode", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "started episode" in text:
                break
        assert "started episode" in text


@pytest.mark.asyncio
async def test_start_episode_passes_the_shot_beat_input_through(monkeypatch):
    """Kevin, 2026-07-28: 'I clicked run 5 clips... I see no obvious
    observables' — root cause traced to episodes starting with zero
    shots. This is the pane-side half of the fix: whatever's typed in
    #movie-pane-shot-beat must reach run_start_episode's beat= kwarg."""
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="EpFilm Pane Test2"), SETTINGS.paths.data_dir)
    set_focus("epfilm-pane-test2", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions

    received = {}

    async def fake_run_start_episode(series_slug, *, title="", beat="", on_wait=None, data_dir=None, sandbox_dir=None):
        received["beat"] = beat
        return "started episode ep-epfilm-s01-e01-abc1234 — shot 1 queued — ready to Advance"
    monkeypatch.setattr(actions, "run_start_episode", fake_run_start_episode)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "a lone drone crosses the skyline"
        btn = pane.query_one("#movie-pane-start-episode", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "started episode" in text:
                break
        assert received["beat"] == "a lone drone crosses the skyline"


@pytest.mark.asyncio
async def test_add_shot_calls_the_shared_action_with_the_beat_input(monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import movie_generation_actions as actions
    from sovereign_agent.movie_series import set_episode_focus

    set_episode_focus("ep-fake-123", "testing", SETTINGS.paths.data_dir)

    received = {}

    async def fake_run_add_shot(episode_id, beat, *, target_clips=5, data_dir=None, sandbox_dir=None):
        received["episode_id"] = episode_id
        received["beat"] = beat
        return "queued shot 2 (5 clips: 'more action') on episode ep-fake-123"
    monkeypatch.setattr(actions, "run_add_shot", fake_run_add_shot)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "more action"
        btn = pane.query_one("#movie-pane-add-shot", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "queued shot" in text:
                break
        assert received["episode_id"] == "ep-fake-123"
        assert received["beat"] == "more action"


@pytest.mark.asyncio
async def test_add_shot_without_a_beat_is_refused_locally():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import set_episode_focus

    set_episode_focus("ep-fake-456", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "   "
        btn = pane.query_one("#movie-pane-add-shot", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "needs a beat" in str(pane.query_one("#movie-pane-status", Static).render())


@pytest.mark.asyncio
async def test_run_batch_stops_early_on_terminal_outcome(monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import set_episode_focus
    set_episode_focus("ep-x-s01-e01-abc1234", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions

    calls = []
    async def fake_run_advance_episode(episode_id, *, on_wait=None, on_step=None, data_dir=None, sandbox_dir=None):
        calls.append(episode_id)
        return "episode_completed — no shots left to render"
    monkeypatch.setattr(actions, "run_advance_episode", fake_run_advance_episode)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-run5", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "episode_completed" in text:
                break
        assert "episode_completed" in text
        assert len(calls) == 1   # stopped after the FIRST call, not all 5


@pytest.mark.asyncio
async def test_verify_button_calls_the_shared_action(monkeypatch):
    """Kevin, 2026-07-29: 'add a episode verify health and success auto
    checking feature.' The pane-side Verify button, for re-checking any
    episode on demand."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import set_episode_focus
    set_episode_focus("ep-verify-s01-e01-abc1234", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import movie_generation_actions as actions

    calls = []
    async def fake_run_verify_episode_health(episode_id, *, data_dir=None, sandbox_dir=None):
        calls.append(episode_id)
        return "health check passed — 1 shot(s), 1 clip(s) verified real on disk"
    monkeypatch.setattr(actions, "run_verify_episode_health", fake_run_verify_episode_health)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-verify", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "health check" in text:
                break
        assert "health check passed" in text
        assert calls == ["ep-verify-s01-e01-abc1234"]


@pytest.mark.asyncio
async def test_new_project_button_creates_a_named_numbered_project_and_focuses_it():
    """Kevin, 2026-07-28: 'add a new project button and each movie
    project can be named and numbered. Automatically.' No typing: click
    the button, get a real saved project + real focus."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from sovereign_agent.movie_projects import get_focus, list_all
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-new-project", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "created + focused" in text:
                break
        assert "created + focused: Movie Project 1" in text

        projects = list_all(SETTINGS.paths.data_dir)
        assert any(p.title == "Movie Project 1" for p in projects)
        assert get_focus(SETTINGS.paths.data_dir).slug == "movie-project-1"


@pytest.mark.asyncio
async def test_new_project_numbers_increment_past_existing_projects():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    save_project(MovieProject(title="Movie Project 1"), SETTINGS.paths.data_dir)
    save_project(MovieProject(title="Movie Project 2"), SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-new-project", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "created + focused" in text:
                break
        assert "created + focused: Movie Project 3" in text


@pytest.mark.asyncio
async def test_focus_project_button_matches_typed_text_against_real_titles():
    """Kevin, 2026-07-28: 'I need a way to add the project focus. Add a
    way into the menu please' — then later 'combine the five into one
    chat box.' Focus Project now matches whatever's typed in the ONE
    command box against a real project's title instead of a dropdown."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from sovereign_agent.movie_projects import get_focus
    from textual.widgets import Static

    save_project(MovieProject(title="Gamma Reel"), SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "gamma"

        btn = pane.query_one("#movie-pane-focus-project", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "focused" in text:
                break
        assert "focused: Gamma Reel" in text
        assert get_focus(SETTINGS.paths.data_dir).slug == "gamma-reel"
        header = str(pane.query_one("#movie-pane-header", Static).render())
        assert "Gamma Reel" in header


@pytest.mark.asyncio
async def test_focus_project_with_no_match_reports_available_titles():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    save_project(MovieProject(title="Delta Reel"), SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "nonexistent title"
        btn = pane.query_one("#movie-pane-focus-project", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "no project title matches" in text:
                break
        assert "no project title matches" in text
        assert "Delta Reel" in text


@pytest.mark.asyncio
async def test_focus_project_with_an_empty_box_is_refused_locally():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-focus-project", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "type (part of) a project" in str(pane.query_one("#movie-pane-status", Static).render())


# ── content safety levels (Kevin, 2026-07-29: "add movie production
# guardrails also so movies are social media platform friendly... add
# safety levels. Which can be applied per series") ─────────────────────────


@pytest.mark.asyncio
async def test_set_safety_level_via_command_box_persists_on_the_series():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import load_series_by_slug, save_series, Series
    save_project(MovieProject(title="Guarded Show"), SETTINGS.paths.data_dir)
    set_focus("guarded-show", "testing", SETTINGS.paths.data_dir)
    save_series(Series(title="Guarded Show"), SETTINGS.paths.data_dir)   # default: strict

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane._set_safety_level("moderate")
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "safety level set" in text:
                break
        assert "safety level set to 'moderate'" in text
        assert load_series_by_slug("guarded-show", SETTINGS.paths.data_dir).safety_level == "moderate"


@pytest.mark.asyncio
async def test_set_safety_level_auto_creates_a_series_if_none_exists_yet():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import load_series_by_slug
    save_project(MovieProject(title="Brand New Show"), SETTINGS.paths.data_dir)
    set_focus("brand-new-show", "testing", SETTINGS.paths.data_dir)
    assert load_series_by_slug("brand-new-show", SETTINGS.paths.data_dir) is None

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane._set_safety_level("open")
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "safety level set" in text:
                break
        assert "safety level set to 'open'" in text
        series = load_series_by_slug("brand-new-show", SETTINGS.paths.data_dir)
        assert series is not None and series.safety_level == "open"


@pytest.mark.asyncio
async def test_set_safety_level_rejects_an_unknown_level():
    from sovereign_agent.config import SETTINGS
    save_project(MovieProject(title="Unknown Level Show"), SETTINGS.paths.data_dir)
    set_focus("unknown-level-show", "testing", SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane._set_safety_level("anything-goes")
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "unknown safety level" in text:
                break
        assert "unknown safety level" in text


@pytest.mark.asyncio
async def test_header_shows_the_current_safety_level():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_series import Series, save_series
    save_project(MovieProject(title="Visible Safety Show"), SETTINGS.paths.data_dir)
    set_focus("visible-safety-show", "testing", SETTINGS.paths.data_dir)
    save_series(Series(title="Visible Safety Show", safety_level="moderate"), SETTINGS.paths.data_dir)

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        header = str(pane.query_one("#movie-pane-header", Static).render())
        assert "moderate" in header


# ── one command box: keyword dispatch (Kevin, 2026-07-28: "combine the
# five into one chat box that feels powerful and natural and immersive,
# not confusing") ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_go_dispatch_routes_every_keyword_to_the_right_action(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)

        cases = [
            ("focus my sci-fi project", "_focus_project", ("my sci-fi project",)),
            ("new project", "_new_project", ()),
            ("storyboard: a red cube", "_generate_storyboard", ("a red cube",)),
            ("board: a red cube", "_generate_storyboard", ("a red cube",)),
            ("clip: a cube spinning", "_generate_clip", ("a cube spinning",)),
            ("pitch a hopeful future", "_draft_pitches", ("a hopeful future",)),
            ("add shot: a second lantern", "_add_shot", ("a second lantern",)),
            ("start: the opening shot", "_start_episode", ("the opening shot",)),
            ("advance", "_advance_episode", ()),
            ("run", "_run_episode_batch", ()),
            ("pause", "_pause_episode", ()),
            ("resume", "_resume_episode", ()),
            ("assemble", "_assemble_episode", ()),
            ("verify", "_verify_episode", ()),
            ("safety moderate", "_set_safety_level", ("moderate",)),
            ("auto series", "_auto_series", ()),
            ("stop", "_stop_auto_series", ()),
        ]
        for text, method_name, expected_args in cases:
            calls = []
            monkeypatch.setattr(pane, method_name, lambda *a: calls.append(a))
            pane.query_one("#movie-pane-command", Input).value = text
            pane._dispatch_command()
            assert calls == [expected_args], f"{text!r} should route to {method_name}{expected_args}"


@pytest.mark.asyncio
async def test_go_dispatch_on_unrecognized_text_falls_through_to_the_nl_classifier(monkeypatch):
    """Kevin, 2026-07-28: 'we want full natural language autonomy.' Text
    that matches no keyword must not silently do nothing or show a
    canned refusal — it goes to the real classifier."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static
    import sovereign_agent.movie_series_auto as auto_mod

    async def fake_classify(text):
        return ("clip", "a lonely lighthouse keeper")
    monkeypatch.setattr(auto_mod, "classify_command", fake_classify)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        clip_calls = []
        monkeypatch.setattr(pane, "_generate_clip", lambda arg=None: clip_calls.append(arg))
        pane.query_one("#movie-pane-command", Input).value = "make something about a lighthouse keeper"
        pane._dispatch_command()
        # synchronous part: the busy guard fires + a "thinking" toast, before
        # the (mocked, but still async/threaded) classifier resolves.
        assert "thinking" in str(pane.query_one("#movie-pane-status", Static).render())
        for _ in range(100):
            await pilot.pause(0.05)
            if clip_calls:
                break
        assert clip_calls == ["a lonely lighthouse keeper"]


@pytest.mark.asyncio
async def test_classifier_fallback_on_unknown_action_shows_the_help_message(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static
    import sovereign_agent.movie_series_auto as auto_mod

    async def fake_classify(text):
        return ("unknown", text)
    monkeypatch.setattr(auto_mod, "classify_command", fake_classify)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "something nobody wrote a rule for"
        pane._dispatch_command()
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "didn't recognize" in text:
                break
        assert "didn't recognize" in text


@pytest.mark.asyncio
async def test_classifier_fallback_never_raises_when_the_model_call_fails(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static
    import sovereign_agent.movie_series_auto as auto_mod

    async def fake_classify(text):
        raise RuntimeError("ollama unreachable")
    monkeypatch.setattr(auto_mod, "classify_command", fake_classify)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane.query_one("#movie-pane-command", Input).value = "do the thing"
        pane._dispatch_command()
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "couldn't understand" in text:
                break
        assert "couldn't understand" in text
        assert "RuntimeError" in text


@pytest.mark.asyncio
async def test_classifier_fallback_second_click_while_thinking_is_refused(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        calls = []
        monkeypatch.setattr(pane, "_command_fallback_worker", lambda text: calls.append(text))
        pane.query_one("#movie-pane-command", Input).value = "no keyword matches this at all"
        pane._dispatch_command()
        pane._dispatch_command()   # immediately again — no yield in between
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_go_dispatch_on_empty_box_asks_for_text():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane._dispatch_command()
        assert "type something first" in str(pane.query_one("#movie-pane-status", Static).render())


@pytest.mark.asyncio
async def test_go_button_and_enter_submit_both_dispatch(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        calls = []
        monkeypatch.setattr(pane, "_advance_episode", lambda: calls.append(1))

        pane.query_one("#movie-pane-command", Input).value = "advance"
        btn = pane.query_one("#movie-pane-go", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        assert calls == [1]

        from textual.widgets import Input as _Input
        pane.on_input_submitted(_Input.Submitted(pane.query_one("#movie-pane-command", Input), "advance"))
        assert calls == [1, 1]


# ── Auto Series (Kevin, 2026-07-28: "the entire system has to manage and
# create an entire series. No human required.") ────────────────────────────


@pytest.mark.asyncio
async def test_auto_series_button_starts_the_worker_when_not_busy(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        calls = []
        monkeypatch.setattr(pane, "_auto_series_worker", lambda: calls.append(1))
        btn = pane.query_one("#movie-pane-auto-series", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        assert calls == [1]
        assert "moviepane-auto-series" in pane._busy


@pytest.mark.asyncio
async def test_second_auto_series_click_while_running_is_refused(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        calls = []
        monkeypatch.setattr(pane, "_auto_series_worker", lambda: calls.append(1))
        pane._auto_series()
        pane._auto_series()
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_stop_auto_series_flips_the_flag_while_running():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane._busy.add("moviepane-auto-series")
        assert pane._auto_series_stop_flag is False
        pane._stop_auto_series()
        assert pane._auto_series_stop_flag is True


@pytest.mark.asyncio
async def test_stop_auto_series_when_not_running_is_a_no_op():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        pane._stop_auto_series()
        assert pane._auto_series_stop_flag is False
        assert "isn't running" in str(pane.query_one("#movie-pane-status", Static).render())


@pytest.mark.asyncio
async def test_auto_series_arms_a_new_session_when_none_active_and_runs(monkeypatch):
    """Confirms the real worker (not just the busy-guard) arms
    AutoCrownStore via the SAME mechanism the rest of the app already
    uses when nothing is active yet, then calls run_auto_series with that
    store — never a separate, ungated autonomy mechanism."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.movie_pane import MoviePane
    from textual.widgets import Static
    import sovereign_agent.auto_crown as auto_crown_mod
    import sovereign_agent.movie_auto_series_runner as runner_mod

    class _FakeStore:
        def __init__(self):
            self.started = None

        def status(self):
            return None

        def is_expired(self):
            return False

        def get_max_trust_tier(self):
            return 1

        def start(self, hours, tier, reason, session_id):
            self.started = (hours, tier, reason)

    fake_store = _FakeStore()
    monkeypatch.setattr(auto_crown_mod, "get_auto_crown_store", lambda: fake_store)

    received = {}

    async def fake_run_auto_series(*, data_dir, sandbox_dir, on_status=None, should_stop=None,
                                   auto_crown_store=None):
        received["store"] = auto_crown_store
        if on_status:
            on_status("designed + focused new series: Test")
        return "stopped — Auto session ended (completed 3 clip step(s))"
    monkeypatch.setattr(runner_mod, "run_auto_series", fake_run_auto_series)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-auto-series", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(pane.query_one("#movie-pane-status", Static).render())
            if "stopped" in text:
                break
        assert "stopped" in text
        assert fake_store.started is not None
        assert fake_store.started[1] == 1   # tier
        assert received["store"] is fake_store


@pytest.mark.asyncio
async def test_full_movie_studio_button_opens_the_modal():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.cockpit.movie_pane import MoviePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#movie-pane", MoviePane)
        btn = pane.query_one("#movie-pane-full-studio", Button)
        pane.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
