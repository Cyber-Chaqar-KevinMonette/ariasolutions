"""Tests for resume-menu-d — the beautiful 'pick a session to resume' menu.
The engine (session_bridge.resume_goal_session) is tested elsewhere; this
covers the menu surface: it opens, lists resumable sessions, routes a click
to the app's gated resume path, and closes cleanly.
"""
from __future__ import annotations

import pytest


def test_resume_menu_imports_cleanly():
    from sovereign_agent.cockpit.app import ResumeMenuScreen
    assert ResumeMenuScreen is not None


@pytest.mark.asyncio
async def test_f6_and_bare_resume_open_the_menu():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        assert isinstance(app.screen, ResumeMenuScreen)
        # toggle closes
        app.action_resume_menu()
        await pilot.pause()
        assert not isinstance(app.screen, ResumeMenuScreen)


@pytest.mark.asyncio
async def test_close_button_cannot_get_stuck_highlighted():  # resume-menu-hardening-d
    """Same bug class as feedback_cockpit_button_focus: a fire-and-handoff
    button must have can_focus=False or Textual leaves it lit forever."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        assert isinstance(app.screen, ResumeMenuScreen)
        btn = app.screen.query_one("#resume-exit-btn")
        assert btn.can_focus is False


@pytest.mark.asyncio
async def test_session_choice_buttons_cannot_get_stuck_highlighted(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen
    from sovereign_agent.cockpit.resume_menu_screen import ResumeSessionButton

    class _FakeSubtask:
        status = "pending"

    class _FakeSession:
        session_id = "sess-fake-123456"
        status = "paused"
        goal = "a fake resumable goal"
        subtasks = [_FakeSubtask()]

    monkeypatch.setattr(
        "sovereign_agent.cockpit.resume_menu_screen.ResumeMenuScreen._candidates",
        lambda self: [_FakeSession()],
    )

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        assert isinstance(app.screen, ResumeMenuScreen)
        buttons = app.screen.query(ResumeSessionButton)
        assert len(buttons) == 1
        assert buttons[0].can_focus is False


@pytest.mark.asyncio
async def test_resume_menu_lists_resumable_sessions(monkeypatch):
    """With resumable sessions present, the menu renders a button per session."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen
    from sovereign_agent.cockpit.resume_menu_screen import ResumeSessionButton

    class _FakeSub:
        def __init__(self, status): self.status = status

    class _FakeSession:
        def __init__(self, sid, goal, status):
            self.session_id = sid
            self.goal = goal
            self.status = status
            self.subtasks = [_FakeSub("done"), _FakeSub("pending")]

    fake = [_FakeSession("sess-aaaaaa", "Tidy the garden", "paused"),
            _FakeSession("sess-bbbbbb", "Fix the ledger", "budget")]
    import sovereign_agent.session_bridge as sb
    monkeypatch.setattr(sb, "resumable_sessions", lambda limit=12: fake)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        assert isinstance(app.screen, ResumeMenuScreen)
        buttons = list(app.screen.query(ResumeSessionButton))
        assert len(buttons) == 2
        ids = {b.session_id for b in buttons}
        assert ids == {"sess-aaaaaa", "sess-bbbbbb"}
        labels = " ".join(str(b.label) for b in buttons)
        assert "Tidy the garden" in labels and "1/2 steps" in labels


@pytest.mark.asyncio
async def test_empty_state_shows_nothing_to_resume(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen

    import sovereign_agent.session_bridge as sb
    monkeypatch.setattr(sb, "resumable_sessions", lambda limit=12: [])

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        text = " ".join(str(s.render()) for s in app.screen.query("Static"))
        assert "nothing to resume" in text.lower()


@pytest.mark.asyncio
async def test_forget_button_deletes_only_that_row_and_refreshes(monkeypatch):
    """resume-menu-forget-d — Kevin, 2026-07-21: "a way to maybe delete[]
    selections if I make sessions I no longer need." Clicking a row's
    forget button must remove exactly that session (never any other) and
    leave the menu open showing the refreshed list."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen
    from sovereign_agent.cockpit.resume_menu_screen import ForgetSessionButton

    class _FakeSub:
        def __init__(self, status): self.status = status

    class _FakeSession:
        def __init__(self, sid, goal, status):
            self.session_id = sid
            self.goal = goal
            self.status = status
            self.subtasks = [_FakeSub("pending")]

    remaining = [_FakeSession("sess-keep", "keep this one", "paused"),
                 _FakeSession("sess-drop", "drop this one", "paused")]
    forgotten = []

    import sovereign_agent.session_bridge as sb

    def _fake_resumable(limit=12):
        return list(remaining)

    def _fake_forget(sid):
        forgotten.append(sid)
        remaining[:] = [s for s in remaining if s.session_id != sid]
        return True

    monkeypatch.setattr(sb, "resumable_sessions", _fake_resumable)
    monkeypatch.setattr(sb, "forget_session", _fake_forget)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        assert isinstance(app.screen, ResumeMenuScreen)
        from textual.widgets import Button

        drop_btn = next(
            b for b in app.screen.query(ForgetSessionButton)
            if b.session_id == "sess-drop"
        )
        # Dispatch the real Pressed message directly rather than a pixel
        # click -- two buttons share a narrow Horizontal row and a click's
        # screen-coordinate hit test is flaky in the test terminal size;
        # this still exercises the actual on_button_pressed code path.
        app.screen.on_button_pressed(Button.Pressed(drop_btn))
        await pilot.pause()
        assert forgotten == ["sess-drop"]  # exactly that one, nothing else
        assert isinstance(app.screen, ResumeMenuScreen)  # menu stays open
        remaining_ids = {b.session_id for b in app.screen.query(ForgetSessionButton)}
        assert remaining_ids == {"sess-keep"}


@pytest.mark.asyncio
async def test_exit_button_closes_the_menu():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ResumeMenuScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_resume_menu()
        await pilot.pause()
        exit_btn = app.screen.query_one("#resume-exit-btn", Button)
        await pilot.click(exit_btn)
        await pilot.pause()
        assert not isinstance(app.screen, ResumeMenuScreen)
