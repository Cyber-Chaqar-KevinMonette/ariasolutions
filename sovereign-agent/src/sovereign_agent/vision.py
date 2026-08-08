"""vision.py — Screen perception stack (M45).

CPU-first. No VRAM consumed for routine capture.
OCR via tesseract subprocess (system, no Python deps) or easyocr if available.
Rolling visual memory: last 5 scenes, session-scoped.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── VisualScene ───────────────────────────────────────────────────────────────


@dataclass
class VisualScene:
    captured_at: str
    screenshot_path: Optional[str]
    text_blocks: list[dict]          # [{text, confidence}]
    window_titles: list[str]
    focused_app: Optional[str]
    inferred_context: str            # heuristic summary
    ocr_elapsed_ms: int
    scene_hash: str                  # SHA-256[:16] of OCR text


    def as_dict(self) -> dict:
        return asdict(self)

    def full_text(self) -> str:
        return " ".join(b.get("text", "") for b in self.text_blocks)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── VisionMemory ──────────────────────────────────────────────────────────────


class VisionMemory:
    """Rolling session-scoped visual memory (last 5 scenes)."""

    MAX_SCENES = 5

    def __init__(self) -> None:
        self._scenes: deque[VisualScene] = deque(maxlen=self.MAX_SCENES)

    def push(self, scene: VisualScene) -> None:
        self._scenes.append(scene)

    def latest(self) -> Optional[VisualScene]:
        if not self._scenes:
            return None
        return self._scenes[-1]

    def last_n(self, n: int) -> list[VisualScene]:
        scenes = list(self._scenes)
        return scenes[-n:]

    def diff_from_prev(self) -> dict:
        """Return delta between last 2 scenes."""
        scenes = list(self._scenes)
        if len(scenes) < 2:
            return {"changed": False, "reason": "insufficient_history"}
        prev, curr = scenes[-2], scenes[-1]
        if prev.scene_hash == curr.scene_hash:
            return {"changed": False, "reason": "identical_hash"}
        prev_text = set(prev.full_text().split())
        curr_text = set(curr.full_text().split())
        added = curr_text - prev_text
        removed = prev_text - curr_text
        return {
            "changed": True,
            "prev_hash": prev.scene_hash,
            "curr_hash": curr.scene_hash,
            "words_added": len(added),
            "words_removed": len(removed),
            "sample_added": sorted(added)[:5],
            "sample_removed": sorted(removed)[:5],
        }

    def clear(self) -> None:
        self._scenes.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────


_vision_memory: Optional[VisionMemory] = None


def get_vision_memory() -> VisionMemory:
    global _vision_memory
    if _vision_memory is None:
        _vision_memory = VisionMemory()
    return _vision_memory


# ── OCR engines ───────────────────────────────────────────────────────────────


def _ocr_tesseract(image_path: Path) -> tuple[list[dict], int]:
    """Run tesseract as subprocess. Requires system tesseract at /usr/bin/tesseract."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["tesseract", str(image_path), "stdout", "--oem", "1", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.returncode != 0:
            return [], elapsed_ms
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        blocks = [{"text": l, "confidence": 0.85} for l in lines]
        return blocks, elapsed_ms
    except (FileNotFoundError, subprocess.TimeoutExpired):
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return [], elapsed_ms


def _ocr_easyocr(image_path: Path) -> tuple[list[dict], int]:
    """Run EasyOCR in CPU mode. Only called if easyocr is installed."""
    start = time.monotonic()
    try:
        import easyocr  # noqa: PLC0415
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        raw = reader.readtext(str(image_path), detail=1)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        blocks = [
            {"text": text, "confidence": float(conf)}
            for _bbox, text, conf in raw
            if conf > 0.3 and text.strip()
        ]
        return blocks, elapsed_ms
    except Exception:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return [], elapsed_ms


def run_ocr(image_path: Path) -> tuple[list[dict], int]:
    """Try easyocr first; fall back to tesseract subprocess."""
    try:
        import easyocr  # noqa: F401, PLC0415
        return _ocr_easyocr(image_path)
    except ImportError:
        pass
    return _ocr_tesseract(image_path)


# ── Context inference ─────────────────────────────────────────────────────────


_CONTEXT_PATTERNS: list[tuple[frozenset[str], str]] = [
    (frozenset({"pytest", "PASSED", "FAILED", "ERROR", "test"}), "running tests"),
    (frozenset({"FAILED", "assert", "Error", "Traceback"}), "debugging test failures"),
    (frozenset({"git", "commit", "push", "branch", "merge"}), "git operations"),
    (frozenset({"def ", "class ", "import", "return", "python"}), "editing Python code"),
    (frozenset({"vim", "nvim", "nano", "emacs"}), "editing in terminal editor"),
    (frozenset({"bash", "zsh", "fish", "$", "~"}), "working in terminal"),
    (frozenset({"Firefox", "Chrome", "http", "www", "html"}), "browsing the web"),
    (frozenset({"sovereign", "cockpit", "aria"}), "working with Aria/cockpit"),
]


def infer_context(text_blocks: list[dict], window_titles: list[str]) -> str:
    all_text = " ".join(b.get("text", "") for b in text_blocks)
    all_text += " " + " ".join(window_titles)

    for keywords, label in _CONTEXT_PATTERNS:
        if any(kw.lower() in all_text.lower() for kw in keywords):
            return label

    if all_text.strip():
        return "general desktop work"
    return "screen captured (no text detected)"


# ── Screenshot capture ────────────────────────────────────────────────────────


def _screenshots_dir() -> Path:
    from sovereign_agent.config import SETTINGS
    d = SETTINGS.paths.data_dir / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def capture_screenshot() -> Optional[Path]:
    """Capture screen. Tries the desktop portal first (Screenshot request,
    verified live on this machine's COSMIC compositor 2026-08-02 — grim
    was returning silent no-ops here since COSMIC doesn't speak grim's
    wlr-screencopy protocol, same root cause already fixed for screen
    recording in portal_screencast.py), falls back to grim for compositors
    where it does work. Returns path or None if both are unavailable."""
    import asyncio
    try:
        from .portal_screenshot import capture_screenshot_via_portal
        portal_path = asyncio.run(capture_screenshot_via_portal())
        if portal_path is not None and portal_path.exists():
            return portal_path
    except Exception:  # noqa: BLE001 — best-effort, fall through to grim
        pass

    shots_dir = _screenshots_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = shots_dir / f"vision-{ts}.png"
    try:
        result = subprocess.run(
            ["grim", str(path)],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0 and path.exists():
            return path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def build_scene(screenshot_path: Optional[Path]) -> VisualScene:
    """Build a VisualScene from a screenshot path (or empty if no screenshot)."""
    text_blocks: list[dict] = []
    ocr_elapsed_ms = 0
    window_titles: list[str] = []

    if screenshot_path and screenshot_path.exists():
        text_blocks, ocr_elapsed_ms = run_ocr(screenshot_path)

    context = infer_context(text_blocks, window_titles)
    full_text = " ".join(b.get("text", "") for b in text_blocks)
    scene_hash = _hash_text(full_text)

    return VisualScene(
        captured_at=datetime.now(timezone.utc).isoformat(),
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        text_blocks=text_blocks,
        window_titles=window_titles,
        focused_app=None,
        inferred_context=context,
        ocr_elapsed_ms=ocr_elapsed_ms,
        scene_hash=scene_hash,
    )
