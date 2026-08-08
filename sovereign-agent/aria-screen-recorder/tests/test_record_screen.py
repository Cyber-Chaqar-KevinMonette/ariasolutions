"""
test_record_screen.py — tests for RecordScreenTool.
No real wf-recorder/Wayland needed — asyncio.create_subprocess_exec is mocked
with a fake Process that models start/SIGINT-stop/hard-kill lifecycles.
"""
from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _mock_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.paths.data_dir = tmp_path
    return s


class _FakeStream:
    def __init__(self, data: bytes = b""):
        self._data = data

    async def read(self):
        return self._data


class _FakeProcess:
    """Models wf-recorder's lifecycle: runs until interrupted, then exits
    once its configured stop signal arrives ('sigint', 'terminate', or
    'kill' — the last two model an unresponsive process needing escalation).
    write_file, if given, is dropped onto disk to simulate a real output."""

    def __init__(self, *, stops_on: str = "sigint", exits_immediately: bool = False,
                 early_returncode: int = 1, stderr: bytes = b"", write_file: Path | None = None):
        self.returncode: int | None = None
        self._exits_immediately = exits_immediately
        self._early_returncode = early_returncode
        self.stderr = _FakeStream(stderr)
        self._stops_on = stops_on
        self._stopped = False
        self.sigint_sent = False
        self.terminated = False
        self.killed = False
        if write_file is not None:
            write_file.parent.mkdir(parents=True, exist_ok=True)
            write_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 50)

    async def wait(self):
        if self._exits_immediately:
            self.returncode = self._early_returncode
            return self.returncode
        if self._stopped:
            self.returncode = 0
            return 0
        await asyncio.sleep(3600)  # "still recording" until stopped

    def send_signal(self, sig):
        if sig == signal.SIGINT:
            self.sigint_sent = True
            if self._stops_on == "sigint":
                self._stopped = True

    def terminate(self):
        self.terminated = True
        if self._stops_on == "terminate":
            self._stopped = True

    def kill(self):
        self.killed = True
        self._stopped = True


def test_record_screen_tool_registered():
    """RecordScreenTool must be in the authority registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "record_screen" in _TIER_REGISTRY
    assert _TIER_REGISTRY["record_screen"].tier == 1


def test_record_screen_tool_tier_is_1():
    from sovereign_agent.tools.record_screen import RecordScreenTool
    assert RecordScreenTool.tier == 1


@pytest.mark.asyncio
async def test_record_screen_wf_recorder_not_found(tmp_path):
    """Returns clear error when wf-recorder binary is missing."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=False),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(tool.Args(), trace_id="t1")

    assert not result.ok
    assert "wf-recorder" in result.error.lower()
    assert "apt install" in result.error


@pytest.mark.asyncio
async def test_record_screen_stops_cleanly_on_sigint(tmp_path):
    """Happy path: recording runs the full duration, SIGINT stops it, file exists."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    captured_cmd = []

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_path = Path(cmd[cmd.index("-f") + 1])
        return _FakeProcess(stops_on="sigint", write_file=out_path)

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(tool.Args(duration_seconds=1.0), trace_id="t2")

    assert result.ok
    assert result.output.endswith(".mp4")
    assert Path(result.output).exists()
    assert "-f" in captured_cmd
    assert "-a" not in captured_cmd
    assert result.metadata["duration_seconds"] == 1.0


@pytest.mark.asyncio
async def test_record_screen_audio_flag(tmp_path):
    """audio=True adds -a to the wf-recorder command."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    captured_cmd = []

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_path = Path(cmd[cmd.index("-f") + 1])
        return _FakeProcess(stops_on="sigint", write_file=out_path)

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(tool.Args(duration_seconds=1.0, audio=True), trace_id="t3")

    assert result.ok
    assert "-a" in captured_cmd
    assert result.metadata["audio"] is True


@pytest.mark.asyncio
async def test_record_screen_geometry_flag(tmp_path):
    """geometry adds -g <geometry> to the wf-recorder command."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    captured_cmd = []

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_path = Path(cmd[cmd.index("-f") + 1])
        return _FakeProcess(stops_on="sigint", write_file=out_path)

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(
            tool.Args(duration_seconds=1.0, geometry="0,0 1920x1080"), trace_id="t4"
        )

    assert result.ok
    assert "-g" in captured_cmd
    assert "0,0 1920x1080" in captured_cmd
    assert result.metadata["geometry"] == "0,0 1920x1080"


@pytest.mark.asyncio
async def test_record_screen_crashed_early_reports_error(tmp_path):
    """If wf-recorder exits before the bounded duration is up, that's a crash, not success."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(exits_immediately=True, early_returncode=1, stderr=b"no wayland display")

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(tool.Args(duration_seconds=1.0), trace_id="t5")

    assert not result.ok
    assert "exited early" in result.error
    assert "no wayland display" in result.error


@pytest.mark.asyncio
async def test_record_screen_hard_kill_fallback_never_leaves_zombie(tmp_path):
    """If wf-recorder ignores SIGINT and terminate(), it gets a hard kill() —
    the tool call always terminates, never leaves a process running."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        out_path = Path(cmd[cmd.index("-f") + 1])
        return _FakeProcess(stops_on="kill", write_file=out_path)

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.record_screen._SIGINT_GRACE_S", 0.05),
        patch("sovereign_agent.tools.record_screen._TERMINATE_GRACE_S", 0.05),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(tool.Args(duration_seconds=1.0), trace_id="t6")

    assert result.ok
    assert Path(result.output).exists()


@pytest.mark.asyncio
async def test_record_screen_custom_filename_sanitized(tmp_path):
    """Custom filename is sanitized and used, with an .mp4 extension."""
    from sovereign_agent.tools.record_screen import RecordScreenTool

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        out_path = Path(cmd[cmd.index("-f") + 1])
        return _FakeProcess(stops_on="sigint", write_file=out_path)

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(
            tool.Args(duration_seconds=1.0, filename="my demo clip!"), trace_id="t7"
        )

    assert result.ok
    assert Path(result.output).name == "my_demo_clip_.mp4"


@pytest.mark.asyncio
async def test_record_screen_metadata_has_next_hint(tmp_path):
    from sovereign_agent.tools.record_screen import RecordScreenTool

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        out_path = Path(cmd[cmd.index("-f") + 1])
        return _FakeProcess(stops_on="sigint", write_file=out_path)

    with (
        patch("sovereign_agent.tools.record_screen._wf_recorder_available", return_value=True),
        patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess_exec),
    ):
        tool = RecordScreenTool()
        result = await tool.execute(tool.Args(duration_seconds=1.0), trace_id="t8")

    assert result.ok
    assert str(Path(result.output)) in result.metadata["next"]
