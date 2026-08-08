"""
test_vision_deep.py — tests for deep vision analysis tools.
No Ollama or Claude API required — all calls are mocked.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_vision(prompt: str, images_b64: list[str], model: str):
    return "Mock analysis: image shows a test pattern.", "mock:test"


@pytest.mark.asyncio
async def test_analyze_image_all_focus(tmp_path):
    """AnalyzeImageTool returns structured analysis for focus='all'."""
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # minimal fake PNG

    from sovereign_agent.tools.image_analyze import AnalyzeImageTool

    with patch(
        "sovereign_agent.tools.image_analyze._vision_call_with_fallback",
        side_effect=_fake_vision,
    ):
        tool = AnalyzeImageTool()
        result = await tool.execute(tool.Args(path=str(img)), trace_id="t1")

    assert result.ok
    assert "Mock analysis" in result.output
    assert result.metadata["focus"] == "all"


@pytest.mark.asyncio
async def test_analyze_image_text_focus(tmp_path):
    """focus='text' routes the correct OCR-focused prompt."""
    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    from sovereign_agent.tools.image_analyze import AnalyzeImageTool

    captured_prompts = []

    async def fake_vision(prompt, images_b64, model):
        captured_prompts.append(prompt)
        return "Line 1\nLine 2\nLine 3", "mock"

    with patch(
        "sovereign_agent.tools.image_analyze._vision_call_with_fallback",
        side_effect=fake_vision,
    ):
        tool = AnalyzeImageTool()
        result = await tool.execute(tool.Args(path=str(img), focus="text"), trace_id="t2")

    assert result.ok
    assert captured_prompts  # a prompt was sent
    assert "text" in captured_prompts[0].lower() or "transcribe" in captured_prompts[0].lower()


@pytest.mark.asyncio
async def test_analyze_image_with_question(tmp_path):
    """A custom question is appended to the prompt."""
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)  # fake JPEG

    from sovereign_agent.tools.image_analyze import AnalyzeImageTool

    captured_prompts = []

    async def fake_vision(prompt, images_b64, model):
        captured_prompts.append(prompt)
        return "The button is blue.", "mock"

    with patch(
        "sovereign_agent.tools.image_analyze._vision_call_with_fallback",
        side_effect=fake_vision,
    ):
        tool = AnalyzeImageTool()
        result = await tool.execute(
            tool.Args(path=str(img), question="What color is the button?"),
            trace_id="t3",
        )

    assert result.ok
    assert "What color is the button?" in captured_prompts[0]


@pytest.mark.asyncio
async def test_analyze_image_file_not_found():
    """AnalyzeImageTool fails gracefully when file doesn't exist."""
    from sovereign_agent.tools.image_analyze import AnalyzeImageTool
    tool = AnalyzeImageTool()
    result = await tool.execute(tool.Args(path="/nonexistent/path/image.png"), trace_id="t4")
    assert not result.ok
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_extract_text_from_image(tmp_path):
    """ExtractTextFromImageTool returns transcribed text."""
    img = tmp_path / "screenshot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    from sovereign_agent.tools.image_analyze import ExtractTextFromImageTool

    async def fake_vision(prompt, images_b64, model):
        return "Hello World\nLine two\nLine three", "mock"

    with patch(
        "sovereign_agent.tools.image_analyze._vision_call_with_fallback",
        side_effect=fake_vision,
    ):
        tool = ExtractTextFromImageTool()
        result = await tool.execute(tool.Args(path=str(img)), trace_id="t5")

    assert result.ok
    assert "Hello World" in result.output
    assert result.metadata["chars"] > 0


@pytest.mark.asyncio
async def test_compare_images_returns_comparison(tmp_path):
    """CompareImagesTool sends both images and returns comparison text."""
    img_a = tmp_path / "before.png"
    img_b = tmp_path / "after.png"
    img_a.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    img_b.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xff" * 100)

    from sovereign_agent.tools.image_analyze import CompareImagesTool

    received_images = []

    async def fake_vision(prompt, images_b64, model):
        received_images.extend(images_b64)
        return "KEY CHANGES: Button moved from left to right.", "mock"

    with patch(
        "sovereign_agent.tools.image_analyze._vision_call_with_fallback",
        side_effect=fake_vision,
    ):
        tool = CompareImagesTool()
        result = await tool.execute(
            tool.Args(path_a=str(img_a), path_b=str(img_b), context="UI diff"),
            trace_id="t6",
        )

    assert result.ok
    assert len(received_images) == 2  # both images sent
    assert "KEY CHANGES" in result.output


def test_vision_tools_registered():
    """All three vision tools must be in the authority registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "analyze_image" in _TIER_REGISTRY
    assert "extract_text_from_image" in _TIER_REGISTRY
    assert "compare_images" in _TIER_REGISTRY
    for name in ("analyze_image", "extract_text_from_image", "compare_images"):
        assert _TIER_REGISTRY[name].tier == 0
