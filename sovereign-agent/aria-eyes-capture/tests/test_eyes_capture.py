"""Behavior tests for aria-eyes-capture (Workstream F) — prove the patched
senses/eyes.py + tools actually work, using a shadow copy of the whole
package (never touches real src/). STAGED ONLY: never promoted — see
test_eyes_capture_live.py for the promoted, plain-import copy.

No camera exists on the dev machine building this (confirmed:
devices.discover_cameras() returns [] here) — the "actually grabs a
frame" path is tested via a mocked subprocess call, honestly documented
as such rather than pretending real hardware was exercised.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-eyes-capture" / "patcher.py").is_file():
            return candidate / "aria-eyes-capture"
    raise RuntimeError("could not locate aria-eyes-capture/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_eyes, patch_senses_tools, patch_tools_init

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    eyes_py = shadow / "sovereign_agent" / "senses" / "eyes.py"
    patched, _ = patch_eyes(eyes_py.read_text(encoding="utf-8"))
    eyes_py.write_text(patched, encoding="utf-8")

    senses_tools_py = shadow / "sovereign_agent" / "tools" / "senses_tools.py"
    patched, _ = patch_senses_tools(senses_tools_py.read_text(encoding="utf-8"))
    senses_tools_py.write_text(patched, encoding="utf-8")

    tools_init_py = shadow / "sovereign_agent" / "tools" / "__init__.py"
    patched, _ = patch_tools_init(tools_init_py.read_text(encoding="utf-8"))
    tools_init_py.write_text(patched, encoding="utf-8")

    return shadow


@pytest.fixture
def shadow_pkg(tmp_path, monkeypatch):
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent
        yield sovereign_agent
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_look_world_and_see_still_work_exactly_as_before(shadow_pkg):
    """Regression guard: the pre-existing read-only status functions must
    be completely unaffected by this addition."""
    from sovereign_agent.senses import eyes

    result = eyes.see()
    assert "seeing" in result
    assert "world" in result
    assert "screen" in result


def test_capture_frame_returns_unavailable_when_no_camera(shadow_pkg):
    from sovereign_agent.senses import eyes

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[]):
        sight = eyes.capture_frame()
    assert sight.available is False
    assert "no camera" in sight.detail.lower()


def test_capture_frame_returns_unavailable_when_no_backend(shadow_pkg):
    from sovereign_agent.senses import devices, eyes

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")
    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value=None):
            sight = eyes.capture_frame()
    assert sight.available is False
    assert "backend" in sight.detail.lower()


def test_capture_frame_succeeds_with_mocked_ffmpeg(shadow_pkg, tmp_path):
    """The actual capture mechanism, exercised via a mocked subprocess call
    since no real camera exists on this dev machine — honestly documented,
    not pretending real hardware was used."""
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


def test_capture_frame_reports_failure_when_subprocess_fails(shadow_pkg, tmp_path):
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


def test_capture_frame_never_raises_on_subprocess_exception(shadow_pkg, tmp_path):
    from sovereign_agent.senses import devices, eyes

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[fake_cam]):
        with mock.patch("shutil.which", return_value="ffmpeg"):
            with mock.patch("subprocess.run", side_effect=RuntimeError("boom")):
                sight = eyes.capture_frame(output_path=tmp_path / "frame.jpg")

    assert sight.available is False
    assert "boom" in sight.detail


@pytest.mark.asyncio
async def test_capture_frame_tool_returns_error_result_when_no_camera(shadow_pkg):
    from sovereign_agent.tools.senses_tools import CaptureFrameTool

    with mock.patch("sovereign_agent.senses.devices.discover_cameras", return_value=[]):
        tool = CaptureFrameTool()
        result = await tool.execute(CaptureFrameTool.Args(), trace_id="t1")

    assert result.ok is False


@pytest.mark.asyncio
async def test_capture_frame_tool_succeeds_with_mocked_camera(shadow_pkg, tmp_path):
    from sovereign_agent.senses import devices
    from sovereign_agent.tools.senses_tools import CaptureFrameTool

    fake_cam = devices.Device(kind="camera", id="video0", name="/dev/video0")

    def fake_run(cmd, **kwargs):
        # the output path is always the last argv element for both
        # ffmpeg and fswebcam command shapes built by capture_frame()
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


def test_capture_frame_tool_registered_in_tools_all(shadow_pkg):
    from sovereign_agent import tools as tools_pkg

    assert "CaptureFrameTool" in tools_pkg.__all__
    assert tools_pkg.CaptureFrameTool is not None
