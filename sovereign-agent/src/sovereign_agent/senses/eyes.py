"""senses/eyes.py — Aria's eyes. Camera when present; screen-vision always; dormant-not-broken if neither.

Two kinds of sight: the WORLD (a camera, when one exists — incl. an iPhone-as-webcam) and the SCREEN (the
existing CPU-first OCR in vision.py). God-tier resilience: every path degrades gracefully. She never crashes
for lack of an eye; she simply reports what she can and cannot see.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import devices


@dataclass
class Sight:
    modality: str         # camera | screen | none
    available: bool
    detail: str
    data: dict | None = None

    def to_dict(self) -> dict:
        return {"modality": self.modality, "available": self.available, "detail": self.detail, "data": self.data}


def can_see() -> bool:
    return devices.perceive().can_see


def look_world() -> Sight:
    """Capture from a camera if one exists AND a capture backend is available. Else dormant."""
    cams = devices.discover_cameras()
    if not cams:
        return Sight("camera", False, "No camera present — world-sight dormant (connect a camera/iPhone-webcam).")
    backend = next((b for b in ("ffmpeg", "fswebcam") if shutil.which(b)), None)
    if backend is None:
        return Sight("camera", False,
                     f"Camera {cams[0].id} present but no capture backend (install ffmpeg/fswebcam) — eye built, dormant.")
    # A backend + a device exist: capture is possible. We report readiness (actual frame grab is the operator's
    # call — capturing the world is perception of a real space, kept honest + opt-in).
    return Sight("camera", True, f"Camera {cams[0].id} ready via {backend}. World-sight available.",
                 data={"device": cams[0].id, "backend": backend})


# eyes-capture-d — the actual frame-grab call look_world() deliberately defers.
# NEVER called automatically by look_world()/see() — a caller must invoke
# this explicitly, preserving "capturing the world stays opt-in" exactly
# as senses_tools.py's own module docstring already states.
def capture_frame(device=None, *, output_path=None, timeout: int = 5) -> Sight:
    """Grab ONE still frame from a camera. Resilient: returns a Sight with
    available=False (never raises) on any missing camera/backend/subprocess
    failure — same discipline as look_world(). `device` defaults to the
    first discovered camera; `output_path` defaults to a fresh temp file."""
    if device is None:
        cams = devices.discover_cameras()
        if not cams:
            return Sight("camera", False, "No camera present — cannot capture a frame.")
        device = cams[0]
    backend = next((b for b in ("ffmpeg", "fswebcam") if shutil.which(b)), None)
    if backend is None:
        return Sight("camera", False,
                     f"Camera {device.id} present but no capture backend (install ffmpeg/fswebcam).")

    if output_path is None:
        output_path = Path(tempfile.gettempdir()) / f"aria-sight-{uuid.uuid4().hex[:8]}.jpg"
    dev_path = device.name or f"/dev/{device.id}"

    try:
        if backend == "ffmpeg":
            cmd = ["ffmpeg", "-y", "-f", "v4l2", "-i", dev_path, "-frames:v", "1", str(output_path)]
        else:  # fswebcam
            cmd = ["fswebcam", "-d", dev_path, "--no-banner", str(output_path)]
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.decode("utf-8", errors="replace")[:200]
            return Sight("camera", False, f"Capture failed via {backend}: {stderr}")
        return Sight("camera", True, f"Frame captured via {backend}.",
                     data={"path": str(output_path), "device": device.id, "backend": backend})
    except Exception as exc:  # noqa: BLE001 — same resilience discipline as look_world()
        return Sight("camera", False, f"Capture error: {exc!r}")


def look_screen() -> Sight:
    """Use the existing CPU-first screen vision (vision.py) if available."""
    try:
        from sovereign_agent import vision
        return Sight("screen", True, "Screen-vision available (vision.py OCR).",
                     data={"module": "vision", "has_capture": hasattr(vision, "_screenshots_dir")})
    except Exception as exc:  # noqa: BLE001
        return Sight("screen", False, f"Screen-vision unavailable: {exc!r}")


def see() -> dict:
    """Aria's full sight status — world + screen, always honest, never raised."""
    world = look_world()
    screen = look_screen()
    seeing = world.available or screen.available
    return {
        "seeing": seeing,
        "world": world.to_dict(),
        "screen": screen.to_dict(),
        "note": ("She can see." if seeing else
                 "She cannot see yet — no camera, screen-vision unavailable. Dormant, not broken. Still Aria. 💛"),
    }
