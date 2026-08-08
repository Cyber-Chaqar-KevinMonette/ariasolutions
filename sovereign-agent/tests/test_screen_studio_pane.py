"""Tests for screen_studio_pane.py — the ✦ screen split-pane recording
studio. Direct Button.Pressed dispatch (not pilot.click), same reason
test_movie_pane.py gives: the pane sits past the default test-terminal's
visible width once #main.screen-split is active."""
from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

import pytest
from textual.widgets import Button, Static


async def _open_pane(pilot):
    app = pilot.app
    btn = app.query_one("#screen-toggle-btn", Button)
    app.on_button_pressed(Button.Pressed(btn))
    await pilot.pause()
    return app


@pytest.mark.asyncio
async def test_toggling_reveals_screen_studio_pane():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.screen_studio_pane import ScreenStudioPane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        main = app.query_one("#main")
        assert "screen-split" in main.classes
        pane = app.query_one("#screen-studio-pane", ScreenStudioPane)
        header = str(pane.query_one("#screen-pane-header", Static).render())
        assert "Screen Studio" in header

        # toggling again hides it
        await _open_pane(pilot)
        assert "screen-split" not in main.classes


@pytest.mark.asyncio
async def test_busy_guard_refuses_second_click_while_recording():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.screen_studio_pane import ScreenStudioPane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#screen-studio-pane", ScreenStudioPane)
        assert pane._try_start("screen-studio-record") is True
        assert pane._try_start("screen-studio-record") is False  # busy
        pane._finish("screen-studio-record")
        assert pane._try_start("screen-studio-record") is True  # released


@pytest.mark.asyncio
async def test_start_recording_reports_missing_capture_backend(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit import screen_recording_session as recsession
    from sovereign_agent.cockpit.screen_studio_pane import ScreenStudioPane

    monkeypatch.setattr(recsession, "recording_available", lambda: False)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#screen-studio-pane", ScreenStudioPane)
        pane._start_recording()
        status = str(pane.query_one("#screen-pane-status", Static).render())
        assert "gst-launch-1.0" in status or "portal" in status
        # busy-guard released even on this early-exit path
        assert pane._try_start("screen-studio-record") is True
        pane._finish("screen-studio-record")


def test_capture_screenshot_to_dir_uses_grim_when_available(tmp_path):
    from sovereign_agent.cockpit.screen_studio_pane import capture_screenshot_to_dir

    def _fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        return mock.MagicMock(returncode=0, stderr=b"")

    with mock.patch("sovereign_agent.tools.screenshot._grim_available", return_value=True), \
         mock.patch("subprocess.run", side_effect=_fake_run):
        ok, msg = capture_screenshot_to_dir(tmp_path)

    assert ok is True
    assert msg.startswith("saved: ")
    assert "portal" not in msg


def test_capture_screenshot_to_dir_falls_back_to_portal(tmp_path):
    from sovereign_agent.cockpit.screen_studio_pane import capture_screenshot_to_dir

    portal_file = tmp_path / "portal-src.png"
    portal_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    async def _fake_portal():
        return portal_file

    with mock.patch("sovereign_agent.tools.screenshot._grim_available", return_value=False), \
         mock.patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
                    side_effect=_fake_portal):
        ok, msg = capture_screenshot_to_dir(tmp_path)

    assert ok is True
    assert "portal" in msg
    saved = Path(msg.split("saved (portal): ", 1)[1])
    assert saved.exists()


def test_capture_screenshot_to_dir_reports_when_both_backends_fail(tmp_path):
    from sovereign_agent.cockpit.screen_studio_pane import capture_screenshot_to_dir

    async def _fake_portal():
        return None

    with mock.patch("sovereign_agent.tools.screenshot._grim_available", return_value=False), \
         mock.patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
                    side_effect=_fake_portal):
        ok, msg = capture_screenshot_to_dir(tmp_path)

    assert ok is False
    assert "grim" in msg.lower()
