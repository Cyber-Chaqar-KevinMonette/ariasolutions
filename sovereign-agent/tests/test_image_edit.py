"""
test_image_edit.py — tests for EditImageTool and InpaintImageTool.
No real diffusers/torch/CUDA needed — all calls mocked.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

import pytest


def _fake_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@contextmanager
def _noop_vram_lock(name):
    yield


def _fake_pil_image(size=(512, 512)):
    """Return a minimal MagicMock that passes size checks."""
    m = MagicMock()
    m.size = size
    return m


def test_edit_image_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "edit_image" in _TIER_REGISTRY
    assert _TIER_REGISTRY["edit_image"].tier == 1


def test_inpaint_image_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "inpaint_image" in _TIER_REGISTRY
    assert _TIER_REGISTRY["inpaint_image"].tier == 1


@pytest.mark.asyncio
async def test_edit_image_invalid_model():
    """Invalid model name returns a clear error."""
    from sovereign_agent.tools.image_edit import EditImageTool

    with patch("sovereign_agent.tools.image_edit._load_pil", return_value=_fake_pil_image()):
        tool = EditImageTool()
        result = await tool.execute(
            tool.Args(path="/fake/img.png", prompt="test", model="unknown-model"),
            trace_id="t1",
        )

    assert not result.ok
    assert "unknown model" in result.error


@pytest.mark.asyncio
async def test_edit_image_file_not_found():
    """Returns error when source image doesn't exist."""
    from sovereign_agent.tools.image_edit import EditImageTool

    tool = EditImageTool()
    result = await tool.execute(
        tool.Args(path="/nonexistent/image.png", prompt="test"),
        trace_id="t2",
    )
    assert not result.ok
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_edit_image_saves_result():
    """Successful edit saves file and returns its path."""
    from sovereign_agent.tools.image_edit import EditImageTool

    png = _fake_png()

    with (
        patch("sovereign_agent.tools.image_edit._load_pil", return_value=_fake_pil_image()),
        patch("sovereign_agent.vram.vram_lock", _noop_vram_lock),
        patch("sovereign_agent.tools.image_edit._sync_edit_sdxl_turbo", return_value=png),
    ):
        tool = EditImageTool()
        result = await tool.execute(
            tool.Args(
                path="/fake/source.jpg",
                prompt="convert to oil painting style",
                model="sdxl-turbo",
                strength=0.5,
            ),
            trace_id="t3",
        )

    assert result.ok
    out = Path(result.output)
    assert out.exists()
    assert out.suffix == ".png"
    assert out.read_bytes() == png


@pytest.mark.asyncio
async def test_edit_image_sd21_model():
    """sd21 model routes to the correct sync function."""
    from sovereign_agent.tools.image_edit import EditImageTool

    png = _fake_png()

    with (
        patch("sovereign_agent.tools.image_edit._load_pil", return_value=_fake_pil_image()),
        patch("sovereign_agent.vram.vram_lock", _noop_vram_lock),
        patch("sovereign_agent.tools.image_edit._sync_edit_sd21", return_value=png),
    ):
        tool = EditImageTool()
        result = await tool.execute(
            tool.Args(path="/fake/source.jpg", prompt="pencil sketch", model="sd21"),
            trace_id="t4",
        )

    assert result.ok
    assert result.metadata["model"] == "sd21"


@pytest.mark.asyncio
async def test_edit_image_metadata():
    """Metadata contains source, model, strength, elapsed, size."""
    from sovereign_agent.tools.image_edit import EditImageTool

    with (
        patch("sovereign_agent.tools.image_edit._load_pil", return_value=_fake_pil_image()),
        patch("sovereign_agent.vram.vram_lock", _noop_vram_lock),
        patch("sovereign_agent.tools.image_edit._sync_edit_sdxl_turbo", return_value=_fake_png()),
    ):
        tool = EditImageTool()
        result = await tool.execute(
            tool.Args(
                path="/fake/source.jpg",
                prompt="winter scene",
                strength=0.6,
                seed=99,
            ),
            trace_id="t5",
        )

    assert result.ok
    m = result.metadata
    assert m["source"] == "/fake/source.jpg"
    assert m["strength"] == 0.6
    assert m["seed"] == 99
    assert "elapsed_seconds" in m
    assert m["size_bytes"] > 0


@pytest.mark.asyncio
async def test_inpaint_size_mismatch():
    """Inpainting fails when mask size doesn't match source."""
    from sovereign_agent.tools.image_edit import InpaintImageTool

    source_img = _fake_pil_image(size=(512, 512))
    mask_img = _fake_pil_image(size=(256, 256))

    call_count = [0]
    def _pil_loader(path):
        call_count[0] += 1
        return source_img if call_count[0] == 1 else mask_img

    with patch("sovereign_agent.tools.image_edit._load_pil", side_effect=_pil_loader):
        tool = InpaintImageTool()
        result = await tool.execute(
            tool.Args(path="/fake/src.png", mask_path="/fake/mask.png", prompt="sky"),
            trace_id="t6",
        )

    assert not result.ok
    assert "size" in result.error.lower() or "match" in result.error.lower()


@pytest.mark.asyncio
async def test_inpaint_saves_result():
    """Successful inpainting saves file and returns path."""
    from sovereign_agent.tools.image_edit import InpaintImageTool

    png = _fake_png()
    same_size_img = _fake_pil_image(size=(512, 512))

    with (
        patch("sovereign_agent.tools.image_edit._load_pil", return_value=same_size_img),
        patch("sovereign_agent.vram.vram_lock", _noop_vram_lock),
        patch("sovereign_agent.tools.image_edit._sync_inpaint", return_value=png),
    ):
        tool = InpaintImageTool()
        result = await tool.execute(
            tool.Args(
                path="/fake/source.png",
                mask_path="/fake/mask.png",
                prompt="replace with blue sky, white clouds",
            ),
            trace_id="t7",
        )

    assert result.ok
    out = Path(result.output)
    assert out.exists()
    assert "inpainted" in out.name


@pytest.mark.asyncio
async def test_edit_missing_dependency():
    """Missing diffusers returns install instructions."""
    from sovereign_agent.tools.image_edit import EditImageTool

    def _raise_import(*a, **kw):
        raise ImportError("No module named 'diffusers'")

    with (
        patch("sovereign_agent.tools.image_edit._load_pil", return_value=_fake_pil_image()),
        patch("sovereign_agent.vram.vram_lock", _noop_vram_lock),
        patch("sovereign_agent.tools.image_edit._sync_edit_sdxl_turbo", side_effect=_raise_import),
    ):
        tool = EditImageTool()
        result = await tool.execute(
            tool.Args(path="/fake/img.png", prompt="test"),
            trace_id="t8",
        )

    assert not result.ok
    assert "pip install" in result.error.lower() or "diffusers" in result.error.lower()
