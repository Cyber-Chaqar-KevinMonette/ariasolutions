"""capture_screenshot() tries the desktop portal first (works on COSMIC,
where grim doesn't), falls back to grim otherwise. Real bug this covers:
COSMIC doesn't implement grim's protocol, and the old code had no
fallback at all — it silently returned a "success" with no screenshot.
"""
from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

from sovereign_agent import vision


def test_uses_portal_result_when_available(tmp_path):
    portal_path = tmp_path / "portal-shot.png"
    portal_path.write_bytes(b"fake png")

    async def _fake_capture():
        return portal_path

    with mock.patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
                    side_effect=_fake_capture), \
         mock.patch("sovereign_agent.vision.subprocess.run") as grim_run:
        result = vision.capture_screenshot()

    assert result == portal_path
    grim_run.assert_not_called()  # portal succeeded — never touched grim


def test_falls_back_to_grim_when_portal_returns_none(tmp_path):
    async def _fake_capture():
        return None

    fake_result = mock.MagicMock(returncode=0)
    with mock.patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
                    side_effect=_fake_capture), \
         mock.patch("sovereign_agent.vision._screenshots_dir", return_value=tmp_path), \
         mock.patch("sovereign_agent.vision.subprocess.run", return_value=fake_result) as grim_run, \
         mock.patch.object(Path, "exists", return_value=True):
        result = vision.capture_screenshot()

    grim_run.assert_called_once()
    assert result is not None


def test_falls_back_to_grim_when_portal_raises(tmp_path):
    async def _fake_capture():
        raise RuntimeError("dbus unavailable")

    fake_result = mock.MagicMock(returncode=0)
    with mock.patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
                    side_effect=_fake_capture), \
         mock.patch("sovereign_agent.vision._screenshots_dir", return_value=tmp_path), \
         mock.patch("sovereign_agent.vision.subprocess.run", return_value=fake_result) as grim_run, \
         mock.patch.object(Path, "exists", return_value=True):
        result = vision.capture_screenshot()

    grim_run.assert_called_once()
    assert result is not None
