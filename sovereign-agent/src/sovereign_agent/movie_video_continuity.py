"""movie_video_continuity — carry the last frame of a clip forward.

movie-studio-d Phase 3 (Kevin, 2026-07-28): "by taking the last frame of
the last [clip] and an intelligent helper system to carry the last frame
and the story forward with surgical and precision accuracy."

`extract_last_frame` is genuinely new territory in this repo — the only
prior ffmpeg subprocess call anywhere is senses/eyes.py's single-still
webcam capture. This mirrors that exact house style: shutil.which backend
discovery, explicit timeout=, subprocess.run(capture_output=True), a
returncode check, stderr truncated to 200 chars, and a never-raising
dataclass result instead of a propagated exception.

`-sseof -1` seeks ~1 second before end-of-file; `-update 1` overwrites the
same output path on every decoded frame, so the LAST write ffmpeg makes is
the true last frame — the standard ffmpeg idiom for this. Clips shorter
than 1 second (all of ours are, at today's proven 9-frame/~1.1s clip size)
still work: ffmpeg clamps a seek past the start to the beginning and just
decodes forward from there, landing on the last frame regardless.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["FrameExtractionResult", "extract_last_frame"]


@dataclass
class FrameExtractionResult:
    ok: bool
    path: str | None
    detail: str


def extract_last_frame(
    video_path: Path, *, output_path: Path | None = None, timeout: int = 30
) -> FrameExtractionResult:
    video_path = Path(video_path)
    if not video_path.is_file():
        return FrameExtractionResult(False, None, f"video file not found: {video_path}")

    backend = shutil.which("ffmpeg")
    if backend is None:
        return FrameExtractionResult(False, None, "ffmpeg not installed — cannot extract last frame.")

    if output_path is None:
        output_path = video_path.with_name(f"{video_path.stem}_last_frame.png")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-sseof", "-1",
        "-i", str(video_path),
        "-update", "1",
        "-q:v", "2",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.decode("utf-8", errors="replace")[:200]
            return FrameExtractionResult(False, None, f"ffmpeg failed: {stderr}")
        return FrameExtractionResult(True, str(output_path), "last frame extracted")
    except subprocess.TimeoutExpired:
        return FrameExtractionResult(False, None, f"ffmpeg timed out after {timeout}s")
    except Exception as exc:  # noqa: BLE001 — same resilience discipline as senses/eyes.py
        return FrameExtractionResult(False, None, f"extraction error: {exc!r}")
