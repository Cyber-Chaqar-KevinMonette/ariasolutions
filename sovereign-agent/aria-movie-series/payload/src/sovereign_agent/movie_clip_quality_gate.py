"""movie_clip_quality_gate — catch a blank/washed-out/degenerate frame
before it becomes the next shot's continuity cursor.

movie-studio-d Phase 3 (Kevin, 2026-07-28): a real incident earlier tonight
— running LTX-Video at distilled-model step counts (8 steps, no guidance)
on the non-distilled base checkpoint produced washed-out/blank output. In
a chained system, a bad frame silently becoming the NEXT shot's condition
image would propagate that failure forward through every subsequent shot.
This module is the guard against that.

Cheap PIL heuristic, deliberately structural, NOT semantic: it catches
"this frame is flat/blank/degenerate" but will happily pass a sharp,
well-exposed frame that doesn't match the prompt at all. A CLIP-score
prompt-adherence check is a real future upgrade (needs another model —
more VRAM contention on this 8GB card) — explicitly deferred, not built
here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["QualityVerdict", "assess_frame", "MIN_STDDEV", "MIN_UNIQUE_COLORS"]

# Below this stddev, a frame reads as ~flat/washed-out/blank. Tuned as a
# conservative starting point — real chained runs may need to adjust this
# once more example frames (good and bad) exist.
MIN_STDDEV = 8.0

# Degenerate frames collapse to a tiny palette even at high resolution.
MIN_UNIQUE_COLORS = 12

# getcolors() returns None past this count instead of the full list — cap
# generously above MIN_UNIQUE_COLORS so a legitimately colorful frame never
# gets misread as "too few colors" just because we stopped counting.
_COLOR_SAMPLE_CAP = 256 * 256 * 256


@dataclass
class QualityVerdict:
    passed: bool
    reason: str
    stddev: float
    mean_luminance: float
    unique_colors_sampled: int


def assess_frame(frame_path: Path) -> QualityVerdict:
    """Never raises for a genuinely missing/unreadable file — returns a
    failing verdict instead, so a caller's retry loop always has a clean
    (passed, reason) to act on rather than needing its own try/except."""
    path = Path(frame_path)
    if not path.is_file():
        return QualityVerdict(False, f"frame file not found: {path}", 0.0, 0.0, 0)

    try:
        from PIL import Image, ImageStat
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            stat = ImageStat.Stat(rgb)
            # Average stddev across R/G/B channels — a single flat/washed
            # frame has near-zero variance in every channel.
            stddev = sum(stat.stddev) / len(stat.stddev)
            mean_luminance = sum(stat.mean) / len(stat.mean)
            colors = rgb.getcolors(maxcolors=_COLOR_SAMPLE_CAP)
            unique = len(colors) if colors is not None else _COLOR_SAMPLE_CAP
    except Exception as exc:  # noqa: BLE001 — unreadable/corrupt image, never crash the caller
        return QualityVerdict(False, f"could not read frame: {exc!r}", 0.0, 0.0, 0)

    if stddev < MIN_STDDEV:
        return QualityVerdict(
            False, f"stddev {stddev:.2f} below MIN_STDDEV={MIN_STDDEV} (flat/washed-out/blank)",
            stddev, mean_luminance, unique,
        )
    if unique < MIN_UNIQUE_COLORS:
        return QualityVerdict(
            False, f"only {unique} unique colors, below MIN_UNIQUE_COLORS={MIN_UNIQUE_COLORS} (degenerate)",
            stddev, mean_luminance, unique,
        )
    return QualityVerdict(True, "passed structural quality gate", stddev, mean_luminance, unique)
