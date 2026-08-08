"""
test_compression.py — Tests for M36 (compression engine + tools).
"""
from __future__ import annotations

import time
import pytest


# ── compress_events unit tests ────────────────────────────────────────────────


def _make_event(flag: str, payload: dict | None = None, age_seconds: float = 400.0) -> dict:
    return {
        "flag": flag,
        "payload": payload or {},
        "created_at": time.time() - age_seconds,
    }


def test_compress_preserves_high_value_events():
    from sovereign_agent.compression import compress_events
    events = [
        _make_event("commit-d", {"message": "fix bug"}),
        _make_event("token-usage-d", {"tokens": 500}),
        _make_event("lesson-d", {"content": "key lesson"}),
    ]
    ctx = compress_events(events)
    assert ctx.preserved_count == 2  # commit-d and lesson-d
    assert ctx.compressed_count >= 1  # token-usage-d compressed
    assert "commit-d" in ctx.summary
    assert "lesson-d" in ctx.summary


def test_compress_counts_low_value_events():
    from sovereign_agent.compression import compress_events
    events = [
        _make_event("token-usage-d") for _ in range(10)
    ]
    ctx = compress_events(events)
    assert ctx.low_count == 10
    assert ctx.preserved_count == 0
    assert "token-usage-d: 10×" in ctx.summary


def test_compress_does_not_include_recent_events():
    from sovereign_agent.compression import compress_events
    old_event = _make_event("commit-d", age_seconds=400)
    recent_event = _make_event("token-usage-d", age_seconds=10)
    ctx = compress_events([old_event, recent_event], min_age_seconds=300)
    assert ctx.preserved_count == 1
    assert ctx.low_count == 0  # recent not compressed
    assert "1 recent events not compressed" in ctx.summary


def test_tokens_saved_estimate_positive_for_many_low_events():
    from sovereign_agent.compression import compress_events
    events = [_make_event("token-usage-d") for _ in range(50)]
    ctx = compress_events(events)
    assert ctx.tokens_saved_estimate > 0


def test_empty_events_returns_empty_summary():
    from sovereign_agent.compression import compress_events
    ctx = compress_events([])
    assert ctx.preserved_count == 0
    assert ctx.compressed_count == 0


def test_extra_preserve_tags_honored():
    from sovereign_agent.compression import compress_events
    events = [_make_event("my-custom-d", {"data": "important"})]
    ctx = compress_events(events, preserve_tags={"my-custom-d"})
    assert ctx.preserved_count == 1
    assert "my-custom-d" in ctx.summary


# ── compression_opportunity_score tests ──────────────────────────────────────


def test_score_zero_for_empty():
    from sovereign_agent.compression import compression_opportunity_score
    assert compression_opportunity_score([]) == 0.0


def test_score_high_for_all_low_value():
    from sovereign_agent.compression import compression_opportunity_score
    events = [_make_event("token-usage-d") for _ in range(10)]
    score = compression_opportunity_score(events)
    assert score > 0.5


def test_score_low_for_all_high_value():
    from sovereign_agent.compression import compression_opportunity_score
    events = [_make_event("commit-d") for _ in range(10)]
    score = compression_opportunity_score(events)
    assert score == 0.0


# ── Tool registration tests ───────────────────────────────────────────────────


def test_compression_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "context_stats" in _TIER_REGISTRY
    assert "compress_context" in _TIER_REGISTRY
    assert "read_compressed_context" in _TIER_REGISTRY
    assert _TIER_REGISTRY["context_stats"].tier == 0
    assert _TIER_REGISTRY["compress_context"].tier == 1
    assert _TIER_REGISTRY["read_compressed_context"].tier == 0


def test_compression_tools_have_failure_modes():
    from sovereign_agent.tools.compression_tools import (
        ContextStatsTool, CompressContextTool, ReadCompressedContextTool
    )
    for cls in (ContextStatsTool, CompressContextTool, ReadCompressedContextTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


@pytest.mark.asyncio
async def test_context_stats_returns_structure():
    from sovereign_agent.tools.compression_tools import ContextStatsTool
    from unittest.mock import patch
    tool = ContextStatsTool()
    with patch("sovereign_agent.tools.compression_tools._load_recent_events", return_value=[]):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "event_count" in result.output
    assert "compression_opportunity" in result.output


@pytest.mark.asyncio
async def test_compress_context_no_events():
    from sovereign_agent.tools.compression_tools import CompressContextTool
    from unittest.mock import patch
    tool = CompressContextTool()
    with patch("sovereign_agent.tools.compression_tools._load_recent_events", return_value=[]):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["compressed"] is False


@pytest.mark.asyncio
async def test_read_compressed_context_no_data():
    from sovereign_agent.tools.compression_tools import ReadCompressedContextTool
    from unittest.mock import patch
    tool = ReadCompressedContextTool()
    with patch("sovereign_agent.tools.compression_tools._query_compression_atoms", return_value=[]):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert not result.ok
    assert "no compression summaries" in result.error


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_compression_oracle_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "compression-oracle-d" in src, "compression-oracle-d missing"
            return
        p = p.parent
    pytest.skip("loop.py not found")
