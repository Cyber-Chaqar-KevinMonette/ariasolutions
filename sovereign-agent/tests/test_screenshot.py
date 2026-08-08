"""
test_screenshot.py — tests for TakeScreenshotTool.
No real grim/Wayland needed — subprocess calls are mocked.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


def _mock_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.paths.data_dir = tmp_path
    return s


def _make_proc(returncode: int = 0, stderr: bytes = b"", write_file: bool = True):
    """Create a mock subprocess.CompletedProcess, optionally writing a fake PNG."""
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stderr = stderr
    m.stdout = b""
    return m


import pytest


def test_screenshot_tool_registered():
    """TakeScreenshotTool must be in the authority registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "take_screenshot" in _TIER_REGISTRY
    assert _TIER_REGISTRY["take_screenshot"].tier == 1


def test_screenshot_tool_tier_is_1():
    from sovereign_agent.tools.screenshot import TakeScreenshotTool
    assert TakeScreenshotTool.tier == 1


@pytest.mark.asyncio
async def test_screenshot_grim_not_found_and_portal_also_fails(tmp_path):
    """Returns clear error when grim is missing AND the portal fallback fails too."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    async def _fake_portal():
        return None

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=False),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
              side_effect=_fake_portal),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(), trace_id="t1")

    assert not result.ok
    assert "grim" in result.error.lower()


@pytest.mark.asyncio
async def test_screenshot_falls_back_to_portal_when_grim_missing(tmp_path):
    """No grim, no geometry/output requested -> portal fallback succeeds."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    portal_file = tmp_path / "portal-src.png"
    portal_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    async def _fake_portal():
        return portal_file

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=False),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.portal_screenshot.capture_screenshot_via_portal",
              side_effect=_fake_portal),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.ok
    assert Path(result.output).exists()
    assert result.metadata["backend"] == "portal"


@pytest.mark.asyncio
async def test_screenshot_geometry_without_grim_errors_clearly(tmp_path):
    """No portal equivalent of -g/-o -> honest error, not a silently-ignored request."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=False),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(geometry="0,0 100x100"), trace_id="t1")

    assert not result.ok
    assert "portal" in result.error.lower()


@pytest.mark.asyncio
async def test_screenshot_captures_full_screen(tmp_path):
    """Full-screen capture writes file and returns its path."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

    def _fake_run(cmd, **kwargs):
        # Write the PNG to the output path (last arg)
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(png)
        return _make_proc(returncode=0)

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.screenshot.subprocess.run", side_effect=_fake_run),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(), trace_id="t2")

    assert result.ok
    assert result.output.endswith(".png")
    assert Path(result.output).exists()
    assert result.metadata["scale"] == 1.0
    assert result.metadata["output"] is None


@pytest.mark.asyncio
async def test_screenshot_with_output_flag(tmp_path):
    """Specifying output monitor adds -o flag to grim command."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    captured_cmd = []

    def _fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        return _make_proc(returncode=0)

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.screenshot.subprocess.run", side_effect=_fake_run),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(output="DP-1"), trace_id="t3")

    assert result.ok
    assert "-o" in captured_cmd
    assert "DP-1" in captured_cmd
    assert result.metadata["output"] == "DP-1"


@pytest.mark.asyncio
async def test_screenshot_with_scale(tmp_path):
    """scale=0.5 adds -s 0.5 to grim command."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    captured_cmd = []

    def _fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        return _make_proc(returncode=0)

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.screenshot.subprocess.run", side_effect=_fake_run),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(scale=0.5), trace_id="t4")

    assert result.ok
    assert "-s" in captured_cmd
    assert "0.5" in captured_cmd
    assert result.metadata["scale"] == 0.5


@pytest.mark.asyncio
async def test_screenshot_grim_nonzero_exit(tmp_path):
    """Non-zero grim exit code returns error with stderr."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch(
            "sovereign_agent.tools.screenshot.subprocess.run",
            return_value=_make_proc(returncode=1, stderr=b"cannot connect to wayland display"),
        ),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(), trace_id="t5")

    assert not result.ok
    assert "wayland" in result.error.lower() or "grim failed" in result.error.lower()


@pytest.mark.asyncio
async def test_screenshot_custom_filename(tmp_path):
    """Custom filename is sanitized and used."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    def _fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        return _make_proc(returncode=0)

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.screenshot.subprocess.run", side_effect=_fake_run),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(
            tool.Args(filename="my custom name!"),
            trace_id="t6",
        )

    assert result.ok
    assert Path(result.output).name.startswith("my_custom_name_")


@pytest.mark.asyncio
async def test_screenshot_metadata_has_next_hint(tmp_path):
    """Metadata includes a next-step hint for chaining with analyze_image."""
    from sovereign_agent.tools.screenshot import TakeScreenshotTool

    def _fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        return _make_proc(returncode=0)

    with (
        patch("sovereign_agent.tools.screenshot._grim_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.screenshot.subprocess.run", side_effect=_fake_run),
    ):
        tool = TakeScreenshotTool()
        result = await tool.execute(tool.Args(), trace_id="t7")

    assert result.ok
    assert "analyze_image" in result.metadata.get("next", "")
