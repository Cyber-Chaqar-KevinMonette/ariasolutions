"""
screenshot.py — screen capture for Aria (Wayland/COSMIC)

Tier 1 tool — captures the screen or a specific window/region using grim
(the standard Wayland screenshot tool on wlroots compositors like Sway).
Saves to data_dir/images/screenshots/ and returns the path so analyze_image
or extract_text_from_image can be called immediately.

NOT installed/functional on this machine's compositor, COSMIC — confirmed
live 2026-08-02, same root cause as the wf-recorder screen-recording bug
(COSMIC doesn't implement wlr-screencopy-unstable-v1, grim's only capture
protocol). Gap closed 2026-08-02: when grim is unavailable, falls back to
the desktop portal (portal_screenshot.py — same backend vision.py's
capture_screenshot() already uses) for the whole-screen case. The portal's
Screenshot request has no equivalent of grim's -g/-o/-s (region/output/
scale) — a single compositor-chosen monitor only, no crop, no scale — so
geometry/output requests still need real grim and fail loudly (not
silently) when grim is missing instead of pretending to honor them.

Optional: slurp (region selector), grimshot (helper), wf-recorder (video).
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


_GRIM_CMD = os.environ.get("AGENT_SCREENSHOT_CMD", "grim")


def _grim_available() -> bool:
    try:
        subprocess.run(
            [_GRIM_CMD, "--version"],
            capture_output=True,
            timeout=3,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class TakeScreenshotTool(Tool):
    """Capture the current screen or a specific output/region to a PNG file.

    Uses grim — the native Wayland screenshot utility. Works on Pop!_OS
    under COSMIC and any other wlroots compositor.

    After capturing, you can immediately call analyze_image or
    extract_text_from_image on the returned path to understand what's
    on screen.

    Args:
      output     — specific monitor output (e.g. "DP-1", "HDMI-A-1").
                   Leave empty for all outputs merged.
      geometry   — capture a region in "x,y WxH" format (e.g. "0,0 1920x1080").
                   Requires knowing the coordinates. Combine with slurp for
                   interactive selection (not available headlessly).
      scale      — scale factor (1.0 = full resolution, 0.5 = half).
                   Smaller is faster to analyze.
      filename   — custom filename (without extension). Auto-generated if omitted.

    Requirements:
      sudo apt install grim        # usually pre-installed on Pop!_OS COSMIC
      # optional for region select:
      sudo apt install slurp
    """

    name = "take_screenshot"
    tier = 1  # Tier 1: writes files to sandbox
    description = (
        "Capture the current Wayland screen to a PNG file — grim when "
        "available (supports output/geometry/scale), else the desktop "
        "portal as a whole-screen-only fallback (COSMIC doesn't implement "
        "grim's protocol). Saves to data_dir/images/screenshots/ and "
        "returns the path. Immediately chain with analyze_image or "
        "extract_text_from_image. Args: output (monitor name), geometry "
        "('x,y WxH'), scale (float), filename — output/geometry require "
        "real grim, no portal equivalent."
    )
    failure_modes = (
        "grim not installed and portal fallback also unavailable/denied",
        "geometry/output requested but only the portal fallback is available "
        "— no crop/monitor-select equivalent, install grim instead",
        "no Wayland display — WAYLAND_DISPLAY must be set",
        "permission denied — check compositor screenshot permissions",
        "invalid output/geometry — list outputs with: sov outputs or wlr-randr",
        "disk full — check data_dir/images/screenshots/",
    )

    class Args(BaseModel):
        output: Optional[str] = Field(
            default=None,
            description="Monitor output name (e.g. 'DP-1'). Leave empty for all monitors.",
        )
        geometry: Optional[str] = Field(
            default=None,
            description="Region in 'x,y WxH' format (e.g. '0,0 1920x1080'). Overrides output.",
        )
        scale: float = Field(
            default=1.0,
            ge=0.1,
            le=2.0,
            description="Scale factor. 0.5 = half resolution (faster to analyze).",
        )
        filename: Optional[str] = Field(
            default=None,
            description="Custom filename without extension. Auto-generated if omitted.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
        if data_dir is None:
            return ToolResult(ok=False, error="data_dir not configured")

        out_dir = Path(data_dir) / "images" / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = int(time.time())
        name = args.filename or f"screenshot_{ts}"
        # Sanitize filename
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
        out_path = out_dir / f"{safe}.png"

        if not _grim_available():
            if args.geometry or args.output:
                return ToolResult(
                    ok=False,
                    error=(
                        "grim not found and the region/output you asked for "
                        "(geometry/output) has no portal equivalent — the "
                        "desktop-portal fallback only captures the whole "
                        "compositor-chosen screen. Install grim for region/"
                        "output capture: sudo apt install grim"
                    ),
                )
            return await self._capture_via_portal(out_path, args)

        # Build grim command
        cmd = [_GRIM_CMD]

        if args.scale != 1.0:
            cmd += ["-s", str(args.scale)]

        if args.geometry:
            cmd += ["-g", args.geometry]
        elif args.output:
            cmd += ["-o", args.output]

        cmd.append(str(out_path))

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
                env={**os.environ},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error="grim timed out (10s) — is Wayland running?")
        except FileNotFoundError:
            return ToolResult(ok=False, error="grim not found — sudo apt install grim")

        elapsed = time.monotonic() - t0

        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace").strip()
            return ToolResult(
                ok=False,
                error=f"grim failed (exit {proc.returncode}): {stderr or '(no stderr)'}",
            )

        if not out_path.exists():
            return ToolResult(ok=False, error="grim exited 0 but no file was written")

        size = out_path.stat().st_size

        return ToolResult(
            ok=True,
            output=str(out_path),
            metadata={
                "path": str(out_path),
                "output": args.output,
                "geometry": args.geometry,
                "scale": args.scale,
                "elapsed_seconds": round(elapsed, 2),
                "size_bytes": size,
                "next": f"analyze_image(path='{out_path}')",
            },
        )

    async def _capture_via_portal(self, out_path: Path, args: "TakeScreenshotTool.Args") -> ToolResult:
        """grim-unavailable fallback: org.freedesktop.portal.Screenshot,
        whole-screen only (no -g/-o/-s equivalent — see module docstring)."""
        from sovereign_agent.portal_screenshot import capture_screenshot_via_portal

        t0 = time.monotonic()
        try:
            portal_path = await capture_screenshot_via_portal()
        except Exception as exc:  # noqa: BLE001 — report, don't crash the tool
            return ToolResult(ok=False, error=f"portal screenshot failed: {exc!r}")
        elapsed = time.monotonic() - t0

        if portal_path is None or not portal_path.exists():
            return ToolResult(
                ok=False,
                error="grim not found (sudo apt install grim) and the "
                      "desktop portal capture also failed (unreachable, "
                      "denied, or unsupported here).",
            )

        data = portal_path.read_bytes()
        out_path.write_bytes(data)
        try:
            portal_path.unlink()
        except OSError:
            pass  # best-effort cleanup of the portal's own temp file

        return ToolResult(
            ok=True,
            output=str(out_path),
            metadata={
                "path": str(out_path),
                "output": None,
                "geometry": None,
                "scale": args.scale,
                "elapsed_seconds": round(elapsed, 2),
                "size_bytes": out_path.stat().st_size,
                "backend": "portal",
                "next": f"analyze_image(path='{out_path}')",
            },
        )
