"""screen_recording_session.py — manual start/stop screen recording for a
human operator, the missing half `tools/record_screen.py`'s bounded
single-call design doesn't cover.

Kevin, 2026-08-01: "integrate a screen recording software into the
cockpit so I can use it as a video recording or screen recording studio."
`RecordScreenTool` (tools/record_screen.py) is built for ARIA to call
herself — one bounded call, duration fixed upfront, blocks until done.
A human clicking Start now and Stop later needs a genuinely different
shape: launch a capture pipeline with no predetermined duration, hold
the process handle across two separate button presses, stop it on
demand.

screen-recording-portal-d (Kevin, 2026-08-02): rewired off wf-recorder
entirely. "no playable file was written" every time, reproduced live —
this machine's compositor (COSMIC) doesn't implement
`wlr-screencopy-unstable-v1`, wf-recorder's only capture protocol; it
exits instantly and writes nothing. COSMIC ships `xdg-desktop-portal-
cosmic`, so the real fix is the standard portal path every modern
compositor supports: negotiate a PipeWire node via
`portal_screencast.request_screencast_session()`, then consume it with a
`gst-launch-1.0 pipewiresrc` pipeline (confirmed live on this machine:
pipewiresrc/videoconvert/openh264enc/mp4mux are all available; ffmpeg's
build here has no PipeWire input support, so GStreamer is the only real
option). wf-recorder is NOT kept as an automatic fallback — it's
confirmed non-functional on this exact machine, so falling back to it
would just reproduce today's silent failure.

Stopping sends SIGINT to gst-launch-1.0, which is its own designed
behavior (SIGINT -> EOS -> the muxer finalizes a valid moov atom) — this
is what actually prevents "no playable file", not a raw kill. Same
stop-signal ladder as before (SIGINT -> wait -> terminate -> wait ->
kill) as a safety net if EOS ever hangs; grace periods still reused from
record_screen.py (generic shutdown timing, not wf-recorder-specific).

Honest limit: the portal's Start() call shows a real OS picker dialog
the first time (by design — user consent, not a bug) that nothing in an
automated tool environment can click through. The negotiation up through
SelectSources was verified live; Start()/OpenPipeWireRemote were not —
see portal_screencast.py's own docstring.
"""
from __future__ import annotations

import asyncio
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sovereign_agent import portal_screencast
from sovereign_agent.tools.record_screen import _SIGINT_GRACE_S, _TERMINATE_GRACE_S

__all__ = ["RecordingHandle", "StopResult", "recording_available", "start", "stop",
           "recordings_dir"]

_GST_LAUNCH_CMD = "gst-launch-1.0"


@dataclass
class RecordingHandle:
    """Held across the two separate button presses (Start now, Stop
    later) — needs both the capture process AND the portal session to
    tear down cleanly."""
    proc: subprocess.Popen
    session: portal_screencast.ScreenCastSession


@dataclass
class StopResult:
    ok: bool
    stderr: str = ""


def recording_available() -> bool:
    """gst-launch-1.0 must be on PATH and the portal must be reachable
    (dbus-next importable — a live portal round-trip is the same cost as
    just attempting the real recording, so that's not pre-checked here)."""
    if not portal_screencast.portal_available():
        return False
    try:
        subprocess.run([_GST_LAUNCH_CMD, "--version"], capture_output=True, timeout=3)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def recordings_dir(data_dir: Path) -> Path:
    # Same folder RecordScreenTool already writes to -- one save location
    # regardless of whether Aria or Kevin triggered the capture.
    out_dir = Path(data_dir) / "recordings" / "screen_video"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def start(out_path: Path) -> RecordingHandle:
    """Negotiate a real ScreenCast portal session (shows an OS picker
    dialog the first call — by design) and launch a GStreamer pipeline
    consuming its PipeWire node straight into an mp4."""
    session = asyncio.run(portal_screencast.request_screencast_session())
    cmd = [
        _GST_LAUNCH_CMD,
        "pipewiresrc", f"fd={session.pipewire_fd}", f"path={session.node_id}",
        "!", "videoconvert",
        "!", "openh264enc",
        "!", "h264parse",
        "!", "mp4mux",
        "!", "filesink", f"location={out_path}",
    ]
    proc = subprocess.Popen(
        cmd, pass_fds=(session.pipewire_fd,),
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    return RecordingHandle(proc=proc, session=session)


def stop(
    handle: RecordingHandle,
    *,
    sigint_grace: float = _SIGINT_GRACE_S,
    terminate_grace: float = _TERMINATE_GRACE_S,
) -> StopResult:
    """SIGINT first (gst-launch-1.0's own clean-EOS shutdown — what
    actually produces a playable file), then the same escalation ladder
    as before as a safety net, then closes the portal session. Returns
    the real stderr text so a future failure is diagnosable instead of a
    silent dead end (the bug that made today's failure unreadable)."""
    proc = handle.proc
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=sigint_grace)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=terminate_grace)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    stderr_text = ""
    if proc.stderr is not None:
        try:
            stderr_text = proc.stderr.read().decode(errors="replace").strip()
        except Exception:  # noqa: BLE001
            pass

    try:
        asyncio.run(handle.session.close())
    except Exception:  # noqa: BLE001 — best-effort teardown, never fatal
        pass

    return StopResult(ok=(proc.returncode == 0), stderr=stderr_text)
