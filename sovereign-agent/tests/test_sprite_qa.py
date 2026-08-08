"""Tests for sprite_qa.py's deterministic sanity checks. remove_background()
itself (rembg/onnxruntime) is real, local, and CPU-only, but not free
(model load + inference) — exercised directly in a couple of these tests
since it's cheap enough (~1-2s) to be worth the real coverage rather than
mocking the one function this module exists to wrap."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from sovereign_agent.sprite_qa import (
    ANTI_COLLAGE_TERMS,
    check_sprite_quality,
    remove_background,
)


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _solid_rgba(size, color) -> bytes:
    return _png_bytes(Image.new("RGBA", size, color))


def _noisy_rgba_with_alpha_variance(size=(64, 64)) -> bytes:
    rng = np.random.default_rng(42)
    rgb = rng.integers(0, 255, size=(size[1], size[0], 3), dtype=np.uint8)
    alpha = np.zeros((size[1], size[0]), dtype=np.uint8)
    alpha[16:48, 16:48] = 255  # a real opaque "subject" region, transparent elsewhere
    arr = np.dstack([rgb, alpha])
    return _png_bytes(Image.fromarray(arr, mode="RGBA"))


def test_rejects_corrupt_bytes():
    result = check_sprite_quality(b"not a png at all", expected_width=64, expected_height=64)
    assert result.ok is False
    assert "unreadable" in result.warnings[0]


def test_rejects_dimension_mismatch():
    png = _solid_rgba((32, 32), (255, 0, 0, 255))
    result = check_sprite_quality(png, expected_width=64, expected_height=64)
    assert result.ok is False
    assert "dimension mismatch" in result.warnings[0]


def test_rejects_degenerate_solid_color():
    png = _solid_rgba((64, 64), (200, 200, 200, 255))
    result = check_sprite_quality(png, expected_width=64, expected_height=64)
    assert result.ok is False
    assert "degenerate" in result.warnings[0]


def test_rejects_all_transparent_alpha():
    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
    alpha = np.zeros((64, 64), dtype=np.uint8)  # nothing survived matting
    arr = np.dstack([rgb, alpha])
    png = _png_bytes(Image.fromarray(arr, mode="RGBA"))
    result = check_sprite_quality(png, expected_width=64, expected_height=64)
    assert result.ok is False
    assert "no foreground" in result.warnings[0]


def test_rejects_all_opaque_alpha_as_matting_noop():
    rng = np.random.default_rng(2)
    rgb = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
    alpha = np.full((64, 64), 255, dtype=np.uint8)  # matting did nothing
    arr = np.dstack([rgb, alpha])
    png = _png_bytes(Image.fromarray(arr, mode="RGBA"))
    result = check_sprite_quality(png, expected_width=64, expected_height=64)
    assert result.ok is False
    assert "no change" in result.warnings[0]


def test_accepts_real_looking_matted_sprite():
    png = _noisy_rgba_with_alpha_variance()
    result = check_sprite_quality(png, expected_width=64, expected_height=64)
    assert result.ok is True
    assert result.png_bytes is not None
    assert result.warnings == []


def test_warns_but_accepts_missing_alpha_channel():
    png = _png_bytes(Image.new("RGB", (64, 64), (0, 0, 0)))
    # RGB, not solid — add noise so it isn't flagged degenerate first
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
    png = _png_bytes(Image.fromarray(arr, mode="RGB"))
    result = check_sprite_quality(png, expected_width=64, expected_height=64)
    assert result.ok is True
    assert any("no alpha channel" in w for w in result.warnings)


def test_anti_collage_terms_present():
    assert "grid" in ANTI_COLLAGE_TERMS
    assert "collage" in ANTI_COLLAGE_TERMS
    assert "sprite sheet" in ANTI_COLLAGE_TERMS


def test_remove_background_real_produces_alpha_variance():
    """Real rembg call (local ONNX U2Net, CPU) — no mocking. A synthetic
    image with a clear central subject on a flat background should come
    back with real alpha variance (something matted out, something kept)."""
    arr = np.full((96, 96, 3), 240, dtype=np.uint8)  # light flat background
    arr[32:64, 32:64] = [200, 30, 30]  # a distinct red square "subject"
    png = _png_bytes(Image.fromarray(arr, mode="RGB"))

    matted = remove_background(png)
    result = check_sprite_quality(matted, expected_width=96, expected_height=96)

    assert result.ok is True, result.warnings
