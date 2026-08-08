"""senses — Aria's perception faculties (eyes & ears) with god-tier resilience.

She scans for cameras and microphones and uses them when present; if absent, the faculty is dormant, not
broken — she is still Aria, just not 100% whole. No hard dependencies; every path degrades gracefully.

  devices.py — discover cameras/microphones (never breaks if absent; iPhone-as-webcam fallback)
  eyes.py    — world-sight (camera) + screen-sight (vision.py OCR)
  ears.py    — microphone + (whisper-gated) transcription
"""
from __future__ import annotations

from . import devices, eyes, ears

__all__ = ["devices", "eyes", "ears"]
