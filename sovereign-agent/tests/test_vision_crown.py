"""test_vision_crown.py — Tests for M45 (Screen Perception Stack)."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── VisualScene tests ─────────────────────────────────────────────────────────


def test_visual_scene_dataclass():
    from sovereign_agent.vision import VisualScene
    scene = VisualScene(
        captured_at="2026-06-20T00:00:00+00:00",
        screenshot_path="/tmp/test.png",
        text_blocks=[{"text": "hello world", "confidence": 0.9}],
        window_titles=["Terminal"],
        focused_app="Terminal",
        inferred_context="working in terminal",
        ocr_elapsed_ms=150,
        scene_hash="abc123def456789a",
    )
    assert scene.full_text() == "hello world"
    d = scene.as_dict()
    assert d["inferred_context"] == "working in terminal"


def test_visual_scene_empty_text():
    from sovereign_agent.vision import VisualScene
    scene = VisualScene(
        captured_at="2026-06-20T00:00:00+00:00",
        screenshot_path=None,
        text_blocks=[],
        window_titles=[],
        focused_app=None,
        inferred_context="screen captured (no text detected)",
        ocr_elapsed_ms=0,
        scene_hash="0" * 16,
    )
    assert scene.full_text() == ""


# ── VisionMemory tests ────────────────────────────────────────────────────────


def _make_scene(text: str, context: str = "terminal") -> "VisualScene":
    from sovereign_agent.vision import VisualScene, _hash_text
    return VisualScene(
        captured_at="2026-06-20T00:00:00+00:00",
        screenshot_path=None,
        text_blocks=[{"text": text, "confidence": 0.9}],
        window_titles=[],
        focused_app=None,
        inferred_context=context,
        ocr_elapsed_ms=100,
        scene_hash=_hash_text(text),
    )


def test_vision_memory_push_and_latest():
    from sovereign_agent.vision import VisionMemory
    mem = VisionMemory()
    assert mem.latest() is None
    s1 = _make_scene("pytest tests")
    mem.push(s1)
    assert mem.latest() is s1


def test_vision_memory_max_5():
    from sovereign_agent.vision import VisionMemory
    mem = VisionMemory()
    for i in range(7):
        mem.push(_make_scene(f"scene {i}"))
    assert len(mem.last_n(10)) == 5


def test_vision_memory_diff_no_change():
    from sovereign_agent.vision import VisionMemory
    mem = VisionMemory()
    s = _make_scene("same text")
    mem.push(s)
    mem.push(s)  # same scene
    diff = mem.diff_from_prev()
    assert diff["changed"] is False


def test_vision_memory_diff_with_change():
    from sovereign_agent.vision import VisionMemory
    mem = VisionMemory()
    mem.push(_make_scene("hello world foo"))
    mem.push(_make_scene("goodbye world bar"))
    diff = mem.diff_from_prev()
    assert diff["changed"] is True
    assert "words_added" in diff


def test_vision_memory_diff_insufficient_history():
    from sovereign_agent.vision import VisionMemory
    mem = VisionMemory()
    mem.push(_make_scene("only one"))
    diff = mem.diff_from_prev()
    assert diff["changed"] is False
    assert diff["reason"] == "insufficient_history"


def test_vision_memory_clear():
    from sovereign_agent.vision import VisionMemory
    mem = VisionMemory()
    mem.push(_make_scene("test"))
    mem.clear()
    assert mem.latest() is None


# ── infer_context tests ───────────────────────────────────────────────────────


def test_infer_context_terminal():
    from sovereign_agent.vision import infer_context
    blocks = [{"text": "PASSED 10 tests"}]
    ctx = infer_context(blocks, [])
    assert "test" in ctx.lower()


def test_infer_context_git():
    from sovereign_agent.vision import infer_context
    blocks = [{"text": "git commit -m feat: add vision"}]
    ctx = infer_context(blocks, [])
    assert "git" in ctx.lower()


def test_infer_context_empty():
    from sovereign_agent.vision import infer_context
    ctx = infer_context([], [])
    assert "no text" in ctx.lower() or "captured" in ctx.lower()


# ── Tool registration tests ───────────────────────────────────────────────────


def test_vision_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "vision_capture" in _TIER_REGISTRY
    assert "vision_scene" in _TIER_REGISTRY
    assert "vision_diff" in _TIER_REGISTRY
    assert "vision_memory" in _TIER_REGISTRY
    assert "vision_deep" in _TIER_REGISTRY
    assert "vision_watch" in _TIER_REGISTRY
    assert _TIER_REGISTRY["vision_capture"].tier == 1
    assert _TIER_REGISTRY["vision_scene"].tier == 0
    assert _TIER_REGISTRY["vision_diff"].tier == 0
    assert _TIER_REGISTRY["vision_memory"].tier == 0
    assert _TIER_REGISTRY["vision_deep"].tier == 1
    assert _TIER_REGISTRY["vision_watch"].tier == 2


def test_vision_tools_have_failure_modes():
    from sovereign_agent.tools.vision_tools import (
        VisionCaptureTool, VisionSceneTool, VisionDiffTool,
        VisionMemoryTool, VisionDeepTool, VisionWatchTool,
    )
    for cls in (VisionCaptureTool, VisionSceneTool, VisionDiffTool,
                VisionMemoryTool, VisionDeepTool, VisionWatchTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── vision_scene tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vision_scene_empty_memory():
    from sovereign_agent.tools.vision_tools import VisionSceneTool
    from sovereign_agent.vision import VisionMemory
    tool = VisionSceneTool()
    mock_mem = VisionMemory()  # empty
    with patch("sovereign_agent.tools.vision_tools.get_vision_memory", return_value=mock_mem):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["scene"] is None


@pytest.mark.asyncio
async def test_vision_scene_returns_latest():
    from sovereign_agent.tools.vision_tools import VisionSceneTool
    from sovereign_agent.vision import VisionMemory
    tool = VisionSceneTool()
    mock_mem = VisionMemory()
    scene = _make_scene("pytest running", "running tests")
    mock_mem.push(scene)
    with patch("sovereign_agent.tools.vision_tools.get_vision_memory", return_value=mock_mem):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["inferred_context"] == "running tests"
    assert result.output["scene"] is not None


# ── vision_capture tool tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vision_capture_with_mocks():
    from sovereign_agent.tools.vision_tools import VisionCaptureTool
    from sovereign_agent.vision import VisionMemory, VisualScene, _hash_text
    tool = VisionCaptureTool()
    mock_mem = VisionMemory()
    mock_scene = VisualScene(
        captured_at="2026-06-20T00:00:00+00:00",
        screenshot_path="/tmp/test.png",
        text_blocks=[{"text": "running tests", "confidence": 0.9}],
        window_titles=["Terminal"],
        focused_app="Terminal",
        inferred_context="running tests",
        ocr_elapsed_ms=200,
        scene_hash=_hash_text("running tests"),
    )
    with (
        patch("sovereign_agent.tools.vision_tools.capture_screenshot", return_value=Path("/tmp/test.png")),
        patch("sovereign_agent.tools.vision_tools.build_scene", return_value=mock_scene),
        patch("sovereign_agent.tools.vision_tools.get_vision_memory", return_value=mock_mem),
    ):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["inferred_context"] == "running tests"
    assert result.output["text_block_count"] == 1


# ── vision_diff tool tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vision_diff_detects_change():
    from sovereign_agent.tools.vision_tools import VisionDiffTool
    from sovereign_agent.vision import VisionMemory
    tool = VisionDiffTool()
    mock_mem = VisionMemory()
    mock_mem.push(_make_scene("hello world"))
    mock_mem.push(_make_scene("goodbye world"))
    with patch("sovereign_agent.tools.vision_tools.get_vision_memory", return_value=mock_mem):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["changed"] is True


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_vision_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "vision-crown-d" in src, "vision-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
