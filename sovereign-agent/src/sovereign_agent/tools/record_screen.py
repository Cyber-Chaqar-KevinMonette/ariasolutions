"""
record_screen.py — real screen VIDEO capture for Aria (Wayland/COSMIC)

Tier 1 tool — records the display to an MP4 using wf-recorder (the video
sibling of the grim screenshot tool, same tool family/author). Saves to
data_dir/recordings/screen_video/ and returns the path.

Kevin, 2026-07-28: "I want screen recording. Real video footage." — for
showcasing the software in his own content, and because a real recording
(not just still frames) may help AI-project work too.

Why a bounded duration rather than separate start/stop tool calls:
wf-recorder has no built-in duration flag (confirmed via `wf-recorder
--help`) — it records until Ctrl+C/SIGINT, which it handles specially to
finalize the container cleanly. Tracking a running subprocess across
separate tool calls would mean persistent state the orchestrator has to
remember to close; a single bounded call can't leave a recording running
forever, matching this repo's existing "never unbounded" instinct (RAM
gate caps, shots_per_episode caps, bot_services.py's systemd discipline
against zombie processes).

This is the tool-calling half of the already-planned `av.capture` catalog
entry (`workflow/catalog.py`) — real Pause/Resume UI + system audio stay
future work under that same entry.

Why wf-recorder over OBS: OBS is GUI-first, for Kevin's own manual
showcase recording. wf-recorder is scriptable/headless-friendly, the
video-capture answer for an AI-driven tool call — same reasoning
screenshot.py already gives for choosing grim over a GUI screenshot tool.
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


_WF_RECORDER_CMD = os.environ.get("AGENT_RECORD_SCREEN_CMD", "wf-recorder")

# How long to wait for a clean SIGINT-triggered exit, then a terminate()
# exit, before a hard kill() — patchable so tests don't wait real seconds.
_SIGINT_GRACE_S = 10.0
_TERMINATE_GRACE_S = 5.0


def _wf_recorder_available() -> bool:
    try:
        subprocess.run(
            [_WF_RECORDER_CMD, "--version"],
            capture_output=True,
            timeout=3,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class RecordScreenTool(Tool):
    """Record the current Wayland screen to an MP4 file using wf-recorder.

    Records for a bounded duration, then stops itself cleanly — this is
    NOT a start/stop pair, so there is never a recording left running
    after the tool call returns.

    After recording, the returned path is a real, playable video file —
    useful for showcasing the software or for AI-project work that needs
    real footage rather than still frames.

    Args:
      duration_seconds — how long to record, 1-120 seconds. Bounded so a
                         single call can never run away indefinitely.
      audio            — also capture system/default audio input.
      geometry         — capture a region in "x,y WxH" format, same
                         convention as take_screenshot's geometry.
      filename         — custom filename (without extension). Auto-generated
                         if omitted.

    Requirements:
      sudo apt install wf-recorder
    """

    name = "record_screen"
    tier = 1  # Tier 1: writes files to sandbox
    description = (
        "Record the current Wayland screen to an MP4 file using wf-recorder, "
        "for a bounded duration (1-120s). Saves to "
        "data_dir/recordings/screen_video/ and returns the path. "
        "Args: duration_seconds (1-120, default 15), audio (bool), "
        "geometry ('x,y WxH'), filename. "
        "Requires wf-recorder installed."
    )
    failure_modes = (
        "wf-recorder not installed — sudo apt install wf-recorder",
        "no Wayland display — WAYLAND_DISPLAY must be set",
        "recording exited early (crashed) — check stderr in the error message",
        "disk full — check data_dir/recordings/screen_video/",
        "wf-recorder ignored the stop signal — hard-killed after a grace period",
    )

    class Args(BaseModel):
        duration_seconds: float = Field(
            default=15.0,
            ge=1.0,
            le=120.0,
            description="How long to record, in seconds (1-120). Bounded — never unbounded.",
        )
        audio: bool = Field(
            default=False,
            description="Also capture system/default audio input.",
        )
        geometry: Optional[str] = Field(
            default=None,
            description="Region in 'x,y WxH' format (e.g. '0,0 1920x1080'). Full screen if omitted.",
        )
        filename: Optional[str] = Field(
            default=None,
            description="Custom filename without extension. Auto-generated if omitted.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        if not _wf_recorder_available():
            return ToolResult(
                ok=False,
                error=(
                    "wf-recorder not found. Install with: sudo apt install wf-recorder\n"
                    "Check with: which wf-recorder"
                ),
            )

        data_dir = SETTINGS.paths.data_dir
        if data_dir is None:
            return ToolResult(ok=False, error="data_dir not configured")

        # A sibling of cockpit/recorder.py's data_dir/recordings/ (that
        # folder's catalog.json/manifest schema is SVG-frame-shaped; a real
        # .mp4 gets its own subfolder rather than colliding with it).
        out_dir = Path(data_dir) / "recordings" / "screen_video"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = int(time.time())
        name = args.filename or f"recording_{ts}"
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
        out_path = out_dir / f"{safe}.mp4"

        cmd = [_WF_RECORDER_CMD, "-f", str(out_path)]
        if args.audio:
            cmd.append("-a")
        if args.geometry:
            cmd += ["-g", args.geometry]

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
            )
        except FileNotFoundError:
            return ToolResult(ok=False, error="wf-recorder not found — sudo apt install wf-recorder")

        # wf-recorder runs until interrupted, so a clean early exit within
        # the bounded window means it crashed — not the happy path.
        try:
            await asyncio.wait_for(proc.wait(), timeout=args.duration_seconds)
            crashed_early = True
        except asyncio.TimeoutError:
            crashed_early = False

        if crashed_early:
            stderr = (await proc.stderr.read()) if proc.stderr else b""
            elapsed = time.monotonic() - t0
            return ToolResult(
                ok=False,
                error=(
                    f"wf-recorder exited early (code {proc.returncode}) after "
                    f"{elapsed:.1f}s: {stderr.decode(errors='replace').strip() or '(no stderr)'}"
                ),
            )

        # Still recording — stop it the way wf-recorder expects (SIGINT),
        # with a bounded fallback so this can never leave a zombie process.
        proc.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(proc.wait(), timeout=_SIGINT_GRACE_S)
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE_S)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        elapsed = time.monotonic() - t0

        if not out_path.exists():
            return ToolResult(ok=False, error="wf-recorder stopped but no file was written")

        size = out_path.stat().st_size
        if size == 0:
            return ToolResult(ok=False, error="wf-recorder wrote an empty file")

        return ToolResult(
            ok=True,
            output=str(out_path),
            metadata={
                "path": str(out_path),
                "duration_seconds": args.duration_seconds,
                "audio": args.audio,
                "geometry": args.geometry,
                "elapsed_seconds": round(elapsed, 2),
                "size_bytes": size,
                "next": f"attach or share '{out_path}'",
            },
        )
