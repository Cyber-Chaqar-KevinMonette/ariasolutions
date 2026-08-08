"""Tests for movie-studio-d — the Movie Studio cockpit screen (real Textual
pilot click-through, mirrors test_game_studio_screen.py's own UI smoke
pattern, including its scroll_visible(animate=False) fix for buttons
below the fold in a tall scrollable form)."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import MovieProject, load, save


@pytest.mark.asyncio
async def test_slash_movies_opens_movie_studio():
    from textual.widgets import Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        await pilot.pause()
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/movies", validation_result=None))
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, MovieStudioScreen)


@pytest.mark.asyncio
async def test_movie_studio_opens_and_saves():
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        app.screen.query_one("#movie-title-input", Input).value = "SmokeFilm"
        app.screen.query_one("#movie-logline", Input).value = "a test logline"
        save_btn = app.screen.query_one("#movie-save-btn", Button)
        save_btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(save_btn)
        await pilot.pause()
        saved = load("SmokeFilm", SETTINGS.paths.data_dir)
        assert saved is not None and saved.logline == "a test logline"


@pytest.mark.asyncio
async def test_movie_studio_browse_carousel():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS

    save(MovieProject(title="One", genre="short-film"), SETTINGS.paths.data_dir)
    save(MovieProject(title="Two", genre="music-video"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        assert app.screen._pi == 0
        nxt = app.screen.query_one("#movie-next", Button)
        nxt.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(nxt)
        await pilot.pause()
        assert app.screen._pi == 1


@pytest.mark.asyncio
async def test_set_focus_without_reason_is_refused():
    from textual.widgets import Button, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_projects import get_focus

    save(MovieProject(title="NoReasonFilm"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        btn = app.screen.query_one("#movie-set-focus", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        assert get_focus(SETTINGS.paths.data_dir).slug is None
        assert "reason" in str(app.screen.query_one("#movie-help", Static).render())


@pytest.mark.asyncio
async def test_set_focus_with_reason_succeeds():
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.movie_projects import get_focus, slugify

    save(MovieProject(title="FocusFilm"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        app.screen.query_one("#movie-focus-reason", Input).value = "operator asked to start here"
        btn = app.screen.query_one("#movie-set-focus", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        focus = get_focus(SETTINGS.paths.data_dir)
        assert focus.slug == slugify("FocusFilm")


@pytest.mark.asyncio
async def test_draft_pitches_queues_a_real_continuation():
    from textual.widgets import Button, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        btn = app.screen.query_one("#movie-draft-pitches", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        help_text = str(app.screen.query_one("#movie-help", Static).render())
        assert "queued" in help_text


@pytest.mark.asyncio
async def test_generate_storyboard_without_prompt_is_refused():
    from textual.widgets import Button, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS

    save(MovieProject(title="StoryboardFilm"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        btn = app.screen.query_one("#movie-gen-storyboard", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        assert "prompt" in str(app.screen.query_one("#movie-help", Static).render())


@pytest.mark.asyncio
async def test_generate_storyboard_calls_the_real_tool(monkeypatch):
    from textual.widgets import Button, Input, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent import ram_gate
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.generate_storyboard_image import GenerateStoryboardImageTool

    # Hardening pass (Kevin, 2026-07-28): this test hung/failed for real
    # once, mid-session, when actual system RAM dipped under the real
    # ram_gate's 2048MB threshold (other test runs + tonight's real GPU
    # work were eating RAM concurrently) — a test asserting tool wiring
    # must never depend on the real machine's live memory state.
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))

    async def fake_execute(self, args, *, trace_id, on_step=None):
        return ToolResult(ok=True, output={"path": "/fake/storyboards/x.png",
                                           "archive_path": "/fake/archive/x.png",
                                           "message": "ok"})
    monkeypatch.setattr(GenerateStoryboardImageTool, "execute", fake_execute)

    save(MovieProject(title="RealCallFilm"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        app.screen.query_one("#movie-storyboard-prompt", Input).value = "a red cube"
        btn = app.screen.query_one("#movie-gen-storyboard", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(app.screen.query_one("#movie-help", Static).render())
            if "generated" in text:
                break
        assert "generated" in text


@pytest.mark.asyncio
async def test_generate_clip_without_prompt_is_refused():
    from textual.widgets import Button, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS

    save(MovieProject(title="ClipFilm"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        btn = app.screen.query_one("#movie-gen-clip", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        assert "prompt" in str(app.screen.query_one("#movie-help", Static).render())


@pytest.mark.asyncio
async def test_generate_clip_calls_the_real_tool(monkeypatch):
    from textual.widgets import Button, Input, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent import ram_gate
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.generate_movie_clip import GenerateMovieClipTool

    # Hardening pass (Kevin, 2026-07-28) — same real-RAM flakiness fix as
    # test_generate_storyboard_calls_the_real_tool above.
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))

    async def fake_execute(self, args, *, trace_id, on_step=None):
        return ToolResult(ok=True, output={"path": "/fake/clips/x.mp4", "message": "ok"})
    monkeypatch.setattr(GenerateMovieClipTool, "execute", fake_execute)

    save(MovieProject(title="RealClipFilm"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)
        app.screen.query_one("#movie-clip-prompt", Input).value = "a red cube"
        btn = app.screen.query_one("#movie-gen-clip", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        for _ in range(100):
            await pilot.pause(0.05)
            text = str(app.screen.query_one("#movie-help", Static).render())
            if "generated" in text:
                break
        assert "generated" in text


@pytest.mark.asyncio
async def test_second_clip_click_while_busy_is_refused_not_raced(monkeypatch):
    """Hardening pass (Kevin, 2026-07-28) — same real bug found+fixed in
    movie_pane.py: @work(exclusive=True, thread=True) only cancels
    bookkeeping, not the actual running thread, so two rapid clicks could
    race and let a stale completion message land after a newer one's."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from sovereign_agent.config import SETTINGS
    from textual.widgets import Input

    save(MovieProject(title="BusyGuardFilm"), SETTINGS.paths.data_dir)
    calls = []
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_movie_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MovieStudioScreen)
        monkeypatch.setattr(screen, "_clip_worker",
                           lambda slug, prompt, title: calls.append((slug, prompt, title)))
        screen.query_one("#movie-clip-prompt", Input).value = "a red cube"

        screen._generate_clip_current()
        screen._generate_clip_current()   # immediately again — no yield in between
        assert len(calls) == 1, "a second click while busy must not start a second worker"
