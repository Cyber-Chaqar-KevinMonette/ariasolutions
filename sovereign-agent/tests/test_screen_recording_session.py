"""test_screen_recording_session.py — tests for the manual start/stop
recording session (cockpit/screen_recording_session.py). Rewritten off
wf-recorder (confirmed non-functional on this machine — COSMIC doesn't
implement wlr-screencopy) onto the portal+GStreamer backend. No real
D-Bus/portal/gst-launch-1.0 needed: portal_screencast.request_screencast_session
and subprocess.Popen are both mocked. subprocess.Popen is mocked with a
fake process that models the SIGINT -> terminate -> kill escalation
ladder, same as before."""
from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign_agent import portal_screencast
from sovereign_agent.cockpit import screen_recording_session as recsession


class _FakePopen:
    """wait(timeout=...) raises TimeoutExpired until `stops_after` calls
    have been made, modelling an unresponsive-then-responsive process."""

    def __init__(self, stops_after: int = 0, returncode: int = 0, stderr_text: bytes = b""):
        self.pid = 1234
        self._wait_calls = 0
        self._stops_after = stops_after
        self.signals_sent: list[int] = []
        self.terminated = False
        self.killed = False
        self.returncode = returncode
        self.stderr = MagicMock()
        self.stderr.read.return_value = stderr_text

    def send_signal(self, sig):
        self.signals_sent.append(sig)

    def wait(self, timeout=None):
        self._wait_calls += 1
        if self._wait_calls <= self._stops_after:
            raise subprocess.TimeoutExpired(cmd="gst-launch-1.0", timeout=timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def _fake_session(node_id=42, fd=17, session_path="/org/.../session/x"):
    session = portal_screencast.ScreenCastSession(
        node_id=node_id, pipewire_fd=fd, session_path=session_path, bus=MagicMock())
    return session


def test_start_negotiates_a_portal_session_and_builds_the_gst_pipeline(tmp_path):
    out_path = tmp_path / "recording_1.mp4"
    fake_session = _fake_session(node_id=42, fd=17)

    with patch.object(portal_screencast, "request_screencast_session",
                      new=AsyncMock(return_value=fake_session)), \
         patch.object(recsession.subprocess, "Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        handle = recsession.start(out_path)

    cmd = mock_popen.call_args.args[0]
    assert cmd[0] == recsession._GST_LAUNCH_CMD
    assert "pipewiresrc" in cmd
    assert "fd=17" in cmd
    assert "path=42" in cmd
    assert f"location={out_path}" in cmd
    assert "mp4mux" in cmd
    assert handle.session is fake_session


def test_start_passes_the_portal_fd_to_the_child_process(tmp_path):
    out_path = tmp_path / "recording_1.mp4"
    fake_session = _fake_session(fd=23)

    with patch.object(portal_screencast, "request_screencast_session",
                      new=AsyncMock(return_value=fake_session)), \
         patch.object(recsession.subprocess, "Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        recsession.start(out_path)

    assert mock_popen.call_args.kwargs["pass_fds"] == (23,)


def test_stop_clean_sigint_no_escalation():
    proc = _FakePopen(stops_after=0)  # first wait() succeeds
    handle = recsession.RecordingHandle(proc=proc, session=_fake_session())
    with patch.object(handle.session, "close", new=AsyncMock()) as mock_close:
        result = recsession.stop(handle, sigint_grace=0.05, terminate_grace=0.05)
    assert proc.signals_sent  # SIGINT was sent
    assert not proc.terminated and not proc.killed
    assert result.ok
    mock_close.assert_awaited_once()


def test_stop_escalates_to_terminate_when_sigint_ignored():
    # First wait() (after SIGINT) times out, second (after terminate) succeeds.
    proc = _FakePopen(stops_after=1)
    handle = recsession.RecordingHandle(proc=proc, session=_fake_session())
    with patch.object(handle.session, "close", new=AsyncMock()):
        recsession.stop(handle, sigint_grace=0.05, terminate_grace=0.05)
    assert proc.terminated
    assert not proc.killed


def test_stop_escalates_to_kill_when_terminate_ignored():
    # Both SIGINT-wait and terminate-wait time out -> hard kill.
    proc = _FakePopen(stops_after=2)
    handle = recsession.RecordingHandle(proc=proc, session=_fake_session())
    with patch.object(handle.session, "close", new=AsyncMock()):
        recsession.stop(handle, sigint_grace=0.05, terminate_grace=0.05)
    assert proc.terminated
    assert proc.killed


def test_stop_surfaces_real_stderr_on_nonzero_exit():
    """The original bug: stderr was captured but never read. A forced
    failure (nonzero returncode + real stderr text) must come back
    through StopResult, not get silently discarded."""
    proc = _FakePopen(stops_after=0, returncode=1,
                      stderr_text=b"pipewiresrc: stream error occurred")
    handle = recsession.RecordingHandle(proc=proc, session=_fake_session())
    with patch.object(handle.session, "close", new=AsyncMock()):
        result = recsession.stop(handle, sigint_grace=0.05, terminate_grace=0.05)
    assert not result.ok
    assert "pipewiresrc: stream error occurred" in result.stderr


def test_recordings_dir_creates_and_returns_path(tmp_path):
    out_dir = recsession.recordings_dir(tmp_path)
    assert out_dir.is_dir()
    assert out_dir == tmp_path / "recordings" / "screen_video"


def test_recording_available_false_when_portal_unavailable():
    with patch.object(portal_screencast, "portal_available", return_value=False):
        assert recsession.recording_available() is False


def test_recording_available_false_when_gst_launch_missing():
    with patch.object(portal_screencast, "portal_available", return_value=True), \
         patch.object(recsession.subprocess, "run", side_effect=FileNotFoundError):
        assert recsession.recording_available() is False


def test_recording_available_true_when_both_present():
    with patch.object(portal_screencast, "portal_available", return_value=True), \
         patch.object(recsession.subprocess, "run", return_value=MagicMock()):
        assert recsession.recording_available() is True
