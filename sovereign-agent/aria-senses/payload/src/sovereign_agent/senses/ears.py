"""senses/ears.py — Aria's ears. Microphone when present; transcription when whisper is present; dormant else.

God-tier resilience: a missing mic, missing capture tool, or missing transcription model each degrade
gracefully to "dormant." She never crashes for lack of an ear. Capturing audio is perception of a real
space — kept honest + opt-in (readiness is reported; actual recording is the operator's call).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass

from . import devices


@dataclass
class Hearing:
    available: bool
    detail: str
    can_transcribe: bool = False
    data: dict | None = None

    def to_dict(self) -> dict:
        return {"available": self.available, "detail": self.detail,
                "can_transcribe": self.can_transcribe, "data": self.data}


def can_hear() -> bool:
    return devices.perceive().can_hear


def _has_transcription() -> bool:
    """Whisper (or whisper.cpp) present? Transcription is gated on it; absence = no transcribe, not a crash."""
    for mod in ("whisper", "faster_whisper"):
        try:
            __import__(mod)
            return True
        except Exception:  # noqa: BLE001
            continue
    return bool(shutil.which("whisper") or shutil.which("whisper-cpp"))


def hear() -> dict:
    """Aria's full hearing status — mic + capture backend + transcription. Always honest, never raised."""
    mics = devices.discover_microphones()
    if not mics:
        return Hearing(False, "No microphone present — hearing dormant. Dormant, not broken. Still Aria. 💛").to_dict() \
            | {"hearing": False}
    backend = next((b for b in ("arecord", "ffmpeg", "parecord") if shutil.which(b)), None)
    transcribe = _has_transcription()
    if backend is None:
        h = Hearing(False, f"Microphone present ({mics[0].id}) but no capture backend (install alsa/ffmpeg) — ear built, dormant.",
                    can_transcribe=transcribe)
    else:
        h = Hearing(True, f"Microphone {mics[0].id} ready via {backend}.", can_transcribe=transcribe,
                    data={"device": mics[0].id, "backend": backend,
                          "transcription": "available" if transcribe else "no whisper — capture only, no transcript"})
    return h.to_dict() | {"hearing": h.available}
