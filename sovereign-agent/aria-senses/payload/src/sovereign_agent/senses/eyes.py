"""senses/eyes.py — Aria's eyes. Camera when present; screen-vision always; dormant-not-broken if neither.

Two kinds of sight: the WORLD (a camera, when one exists — incl. an iPhone-as-webcam) and the SCREEN (the
existing CPU-first OCR in vision.py). God-tier resilience: every path degrades gracefully. She never crashes
for lack of an eye; she simply reports what she can and cannot see.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass

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
