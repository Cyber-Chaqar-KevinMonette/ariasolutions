"""
test_image_gen.py — tests for image generation tool.
No actual diffusion models needed — all GPU calls are mocked.
"""
from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock


# ── helpers ───────────────────────────────────────────────────────────────────


def _fake_png() -> bytes:
    """Minimal valid PNG header bytes."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _mock_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.paths.data_dir = tmp_path
    return s


def _mock_vram(free_mb: int = 7000) -> MagicMock:
    snap = MagicMock()
    snap.free_mb = free_mb
    return snap


def _noop_vram_lock(name):
    """Sync context manager that does nothing."""
    from contextlib import contextmanager
    @contextmanager
    def _cm():
        yield
    return _cm()


# ── tests ─────────────────────────────────────────────────────────────────────


def test_generate_image_tool_registered():
    """GenerateImageTool must be in the authority registry after import."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "generate_image" in _TIER_REGISTRY
    assert _TIER_REGISTRY["generate_image"].tier == 1  # Tier 1: writes files


def test_generate_image_tool_tier_is_1():
    """Confirm tier=1 on the class itself."""
    from sovereign_agent.tools.image_generate import GenerateImageTool
    assert GenerateImageTool.tier == 1


def test_slug_normalizes_text():
    """_slug turns arbitrary text into a filesystem-safe string."""
    from sovereign_agent.tools.image_generate import _slug
    assert _slug("Hello World! (test)") == "hello_world_test"
    assert _slug("a" * 100) == "a" * 40  # capped at 40
    assert "/" not in _slug("path/to/file")


import pytest


@pytest.mark.asyncio
async def test_generate_image_invalid_model(tmp_path):
    """Invalid model name returns a clear error."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram()),
        patch("sovereign_agent.tools.image_generate.vram_lock", side_effect=_noop_vram_lock),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="test", model="nonexistent-model"), trace_id="t1"
        )

    assert not result.ok
    assert "unknown model" in result.error
    assert "nonexistent-model" in result.error


@pytest.mark.asyncio
async def test_generate_image_vram_too_low(tmp_path):
    """Returns error when free VRAM is below the model requirement."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram(free_mb=500)),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="test sunset", model="flux-schnell"), trace_id="t2"
        )

    assert not result.ok
    assert "insufficient VRAM" in result.error
    assert "sd21" in result.error  # should suggest smaller model


@pytest.mark.asyncio
async def test_generate_image_saves_file(tmp_path):
    """Successful generation saves PNG to data_dir/images/generated/."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    png = _fake_png()

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram()),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
        patch("sovereign_agent.tools.image_generate.vram_lock", side_effect=_noop_vram_lock),
        patch.dict("sovereign_agent.tools.image_generate._SYNC_FNS", {"flux-schnell": MagicMock(return_value=png)}),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="a red apple", model="flux-schnell", seed=42),
            trace_id="t3",
        )

    assert result.ok
    saved = Path(result.output)
    assert saved.exists()
    assert saved.suffix == ".png"
    assert saved.read_bytes() == png
    assert "apple" in saved.name  # slug from prompt


@pytest.mark.asyncio
async def test_generate_image_metadata(tmp_path):
    """Result metadata contains expected fields."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram()),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
        patch("sovereign_agent.tools.image_generate.vram_lock", side_effect=_noop_vram_lock),
        patch.dict("sovereign_agent.tools.image_generate._SYNC_FNS", {"sdxl-turbo": MagicMock(return_value=_fake_png())}),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="blue ocean waves", model="sdxl-turbo", width=512, height=384, steps=2, seed=7),
            trace_id="t4",
        )

    assert result.ok
    m = result.metadata
    assert m["model"] == "sdxl-turbo"
    assert m["width"] == 512
    assert m["height"] == 384
    assert m["steps"] == 2
    assert m["seed"] == 7
    assert "elapsed_seconds" in m
    assert "size_bytes" in m
    assert m["size_bytes"] > 0


@pytest.mark.asyncio
async def test_generate_image_import_error(tmp_path):
    """Missing diffusers returns a friendly install instruction."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    def _raise_import(*a, **kw):
        raise ImportError("No module named 'diffusers'")

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram()),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
        patch("sovereign_agent.tools.image_generate.vram_lock", side_effect=_noop_vram_lock),
        patch.dict("sovereign_agent.tools.image_generate._SYNC_FNS", {"flux-schnell": MagicMock(side_effect=_raise_import)}),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="forest at dawn", model="flux-schnell"), trace_id="t5"
        )

    assert not result.ok
    assert "diffusers" in result.error.lower() or "pip install" in result.error.lower()


@pytest.mark.asyncio
async def test_generate_image_sd21_fallback(tmp_path):
    """sd21 model is selectable and uses lower VRAM."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    png = _fake_png()

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram(free_mb=3800)),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
        patch("sovereign_agent.tools.image_generate.vram_lock", side_effect=_noop_vram_lock),
        patch.dict("sovereign_agent.tools.image_generate._SYNC_FNS", {"sd21": MagicMock(return_value=png)}),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="mountain lake at sunrise", model="sd21", steps=20),
            trace_id="t6",
        )

    assert result.ok
    assert result.metadata["model"] == "sd21"


@pytest.mark.asyncio
async def test_generate_image_creates_output_dir(tmp_path):
    """Output dir is created if it doesn't exist yet."""
    from sovereign_agent.tools.image_generate import GenerateImageTool

    # Don't pre-create the images/ dir
    assert not (tmp_path / "images").exists()

    with (
        patch("sovereign_agent.tools.image_generate.SETTINGS", _mock_settings(tmp_path), create=True),
        patch("sovereign_agent.tools.image_generate.read_vram", return_value=_mock_vram()),
        patch("sovereign_agent.tools.image_generate.SAFETY_FLOOR_MB", 200),
        patch("sovereign_agent.tools.image_generate.vram_lock", side_effect=_noop_vram_lock),
        patch.dict("sovereign_agent.tools.image_generate._SYNC_FNS", {"flux-schnell": MagicMock(return_value=_fake_png())}),
    ):
        tool = GenerateImageTool()
        result = await tool.execute(
            tool.Args(prompt="winter forest"), trace_id="t7"
        )

    assert result.ok
    assert (tmp_path / "images" / "generated").is_dir()
