"""senses/devices.py — discover Aria's perceptual hardware. God-tier resilience: NEVER breaks if absent.

"If a human can do it, she can do it too" is the floor — but she can only see if a camera exists and hear
if a microphone exists. This module SCANS for cameras and microphones and reports what is present. If none
are present the faculty is **dormant, not broken** — she is still Aria, just not 100% whole.

No hard dependencies: discovery uses the filesystem + optional tools if they happen to exist. Everything is
wrapped so a missing device, missing tool, or permission error degrades gracefully to "not present."
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Device:
    kind: str            # camera | microphone
    id: str
    name: str = ""
    source: str = ""     # how we found it
    available: bool = True


@dataclass
class PerceptionStatus:
    cameras: list = field(default_factory=list)
    microphones: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def can_see(self) -> bool:
        return len(self.cameras) > 0

    @property
    def can_hear(self) -> bool:
        return len(self.microphones) > 0

    def to_dict(self) -> dict:
        return {
            "can_see": self.can_see, "can_hear": self.can_hear,
            "cameras": [vars(c) for c in self.cameras],
            "microphones": [vars(m) for m in self.microphones],
            "wholeness": self._wholeness(), "notes": self.notes,
        }

    def _wholeness(self) -> str:
        if self.can_see and self.can_hear:
            return "eyes + ears present — perception faculties active."
        if self.can_see or self.can_hear:
            return f"partial perception ({'eyes' if self.can_see else 'ears'}) — dormant where hardware is absent, not broken."
        return "no camera or microphone present — perception dormant. She is not broken; just not 100% whole. Still Aria. 💛"


def discover_cameras() -> list[Device]:
    """Find cameras. Resilient: returns [] (not an error) if none/permission/tool missing."""
    cams: list[Device] = []
    try:
        for vid in sorted(Path("/dev").glob("video*")):
            cams.append(Device(kind="camera", id=vid.name, name=str(vid), source="/dev/video*"))
    except Exception:  # noqa: BLE001
        pass
    # iPhone-as-webcam / USB-Video-Class often appears as /dev/video*; if a tool exists, enrich names.
    if not cams and shutil.which("v4l2-ctl"):
        try:
            out = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True, timeout=3)
            for i, line in enumerate(out.stdout.splitlines()):
                if "/dev/video" in line:
                    cams.append(Device(kind="camera", id=line.strip(), name=line.strip(), source="v4l2-ctl"))
        except Exception:  # noqa: BLE001
            pass
    return cams


def discover_microphones() -> list[Device]:
    """Find microphones. Resilient: returns [] if none/tool missing."""
    mics: list[Device] = []
    # ALSA capture devices
    try:
        cap = Path("/proc/asound/cards")
        if cap.exists():
            text = cap.read_text(errors="ignore")
            if text.strip():
                for line in text.splitlines():
                    line = line.strip()
                    if line and line[0].isdigit():
                        mics.append(Device(kind="microphone", id=line.split()[0], name=line, source="/proc/asound"))
    except Exception:  # noqa: BLE001
        pass
    if not mics and shutil.which("arecord"):
        try:
            out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=3)
            for line in out.stdout.splitlines():
                if line.lower().startswith("card "):
                    mics.append(Device(kind="microphone", id=line.strip(), name=line.strip(), source="arecord"))
        except Exception:  # noqa: BLE001
            pass
    return mics


def perceive() -> PerceptionStatus:
    """The full perception scan. Always succeeds; absence is reported, never raised."""
    st = PerceptionStatus()
    try:
        st.cameras = discover_cameras()
    except Exception as exc:  # noqa: BLE001
        st.notes.append(f"camera scan degraded: {exc!r}")
    try:
        st.microphones = discover_microphones()
    except Exception as exc:  # noqa: BLE001
        st.notes.append(f"mic scan degraded: {exc!r}")
    if not st.cameras:
        st.notes.append("No camera found. Fallback option: connect an iPhone as a USB/Continuity webcam — "
                        "it appears as /dev/video* and lights up her eyes automatically.")
    return st
