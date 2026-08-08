"""Behavior tests for aria-eyes-capture, promoted to live tests/ — tests
the REAL, already-patched `sovereign_agent.senses.eyes` /
`sovereign_agent.tools.senses_tools` directly, no shadow copy, no
`sys.modules` manipulation. See test_eyes_capture.py (staged only) for
the shadow-copy pre-apply version.

No camera exists on the machine this was built on (confirmed:
devices.discover_cameras() returns [] here) — the "actually grabs a
frame" path is tested via a mocked subprocess call, honestly documented
as such.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest


def test_look_world_and_see_still_work_exactly_as_before():
    from sovereign_agent.senses import eyes

    result = eyes.see()
    assert "seeing" in result
    assert "world" in result
    assert "screen" in result


def test_capture_frame_returns_unavailable_when_no_camera():
    from sovereign_agent.senses import eyes

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[]):
        sight = eyes.capture_frame()
    assert sight.available is False
    assert "no camera" in sight.detail.lower()


def test_capture_frame_returns_unavailable_when_no_backend():
    from sovereign_agent.senses import devices, eyes

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")
    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value=None):
            sight = eyes.capture_frame()
    assert sight.available is False
    assert "backend" in sight.detail.lower()


def test_capture_frame_succeeds_with_mocked_ffmpeg(tmp_path):
    from sovereign_agent.senses import devices, eyes

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")
    output_path = tmp_path / "frame.jpg"

    def fake_run(cmd, **kwargs):
        output_path.write_bytes(b"fake jpeg bytes")
        return mock.Mock(returncode=0, stderr=b"")

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value="ffmpeg"):
            with mock.patch("subprocess.run", side_effect=fake_run):
                sight = eyes.capture_frame(output_path=output_path)

    assert sight.available is True
    assert sight.data["path"] == str(output_path)
    assert sight.data["backend"] == "ffmpeg"


def test_capture_frame_reports_failure_when_subprocess_fails(tmp_path):
    from sovereign_agent.senses import devices, eyes

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")

    def fake_run(cmd, **kwargs):
        return mock.Mock(returncode=1, stderr=b"device busy")

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value="ffmpeg"):
            with mock.patch("subprocess.run", side_effect=fake_run):
                sight = eyes.capture_frame(output_path=tmp_path / "frame.jpg")

    assert sight.available is False
    assert "device busy" in sight.detail


def test_capture_frame_never_raises_on_subprocess_exception(tmp_path):
    from sovereign_agent.senses import devices, eyes

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value="ffmpeg"):
            with mock.patch("subprocess.run", side_effect=RuntimeError("boom")):
                sight = eyes.capture_frame(output_path=tmp_path / "frame.jpg")

    assert sight.available is False
    assert "boom" in sight.detail


@pytest.mark.asyncio
async def test_capture_frame_tool_returns_error_result_when_no_camera():
    from sovereign_agent.tools.senses_tools import CaptureFrameTool

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[]):
        tool = CaptureFrameTool()
        result = await tool.execute(CaptureFrameTool.Args(), trace_id="t1")

    assert result.ok is False


@pytest.mark.asyncio
async def test_capture_frame_tool_succeeds_with_mocked_camera(tmp_path):
    from sovereign_agent.senses import devices
    from sovereign_agent.tools.senses_tools import CaptureFrameTool

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"fake jpeg bytes")
        return mock.Mock(returncode=0, stderr=b"")

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value="ffmpeg"):
            with mock.patch("tempfile.gettempdir", return_value=str(tmp_path)):
                with mock.patch("subprocess.run", side_effect=fake_run):
                    tool = CaptureFrameTool()
                    result = await tool.execute(CaptureFrameTool.Args(), trace_id="t1")

    assert result.ok is True
    assert result.output["modality"] == "camera"


def test_capture_frame_tool_registered_in_tools_all():
    from sovereign_agent import tools as tools_pkg

    assert "CaptureFrameTool" in tools_pkg.__all__
    assert tools_pkg.CaptureFrameTool is not None
