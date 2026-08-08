"""
test_cache_crown.py — Tests for M33 (ResponseCache + cache tools).
"""
from __future__ import annotations

import time
import pytest


# ── ResponseCache unit tests ──────────────────────────────────────────────────


def test_cache_miss_returns_none():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    assert c.get("palace_search", {"query": "aria"}) is None


def test_cache_hit_returns_content():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("palace_search", {"query": "aria"}, '{"result": "ok"}')
    hit = c.get("palace_search", {"query": "aria"})
    assert hit == '{"result": "ok"}'


def test_cache_miss_on_different_args():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("memory_search", {"q": "foo"}, "foo result")
    assert c.get("memory_search", {"q": "bar"}) is None


def test_ttl_expiry_evicts_entry():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache(default_ttl=0)
    c.put("memory_search", {"q": "hello"}, "data", ttl=0)
    import time as _t
    _t.sleep(0.01)
    assert c.get("memory_search", {"q": "hello"}) is None


def test_lru_eviction_when_full():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache(maxsize=3)
    c.put("t1", {}, "a")
    c.put("t2", {}, "b")
    c.put("t3", {}, "c")
    c.put("t4", {}, "d")  # should evict t1 (LRU)
    assert c.get("t1", {}) is None
    assert c.get("t4", {}) == "d"


def test_flush_all():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("a", {}, "x")
    c.put("b", {}, "y")
    count = c.flush()
    assert count == 2
    assert c.get("a", {}) is None
    assert c.get("b", {}) is None


def test_flush_by_tool_name():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("palace_search", {"q": "1"}, "r1")
    c.put("memory_search", {"q": "2"}, "r2")
    count = c.flush("palace_search")
    assert count == 1
    assert c.get("palace_search", {"q": "1"}) is None
    assert c.get("memory_search", {"q": "2"}) == "r2"


def test_stats_shows_hit_rate():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("t", {"x": 1}, "val")
    c.get("t", {"x": 1})   # hit
    c.get("t", {"x": 2})   # miss
    stats = c.stats()
    assert stats["total_requests"] == 2
    assert stats["total_hits"] == 1
    assert stats["hit_rate"] == 0.5


def test_stats_entries_by_tool():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("palace_search", {"q": "a"}, "r")
    c.put("palace_search", {"q": "b"}, "r2")
    c.put("memory_search", {"q": "c"}, "r3")
    stats = c.stats()
    assert stats["entries_by_tool"]["palace_search"] == 2
    assert stats["entries_by_tool"]["memory_search"] == 1
    assert stats["size"] == 3


def test_tokens_saved_estimate_grows_with_hits():
    from sovereign_agent.cache import ResponseCache
    c = ResponseCache()
    c.put("t", {}, "val")
    c.get("t", {})   # 1 hit
    c.get("t", {})   # 2nd hit
    stats = c.stats()
    assert stats["session_tokens_saved_estimate"] > 0


# ── Tool registration tests ───────────────────────────────────────────────────


def test_cache_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "cache_stats" in _TIER_REGISTRY
    assert "cache_flush" in _TIER_REGISTRY
    assert _TIER_REGISTRY["cache_stats"].tier == 0
    assert _TIER_REGISTRY["cache_flush"].tier == 1


def test_cache_tools_have_failure_modes():
    from sovereign_agent.tools.cache_tools import CacheStatsTool, CacheFlushTool
    for cls in (CacheStatsTool, CacheFlushTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


@pytest.mark.asyncio
async def test_cache_stats_tool_returns_dict():
    from sovereign_agent.tools.cache_tools import CacheStatsTool
    tool = CacheStatsTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "hit_rate" in result.output
    assert "size" in result.output


@pytest.mark.asyncio
async def test_cache_flush_tool_returns_count():
    from sovereign_agent.tools.cache_tools import CacheFlushTool
    tool = CacheFlushTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "cleared" in result.output


# ── loop.py integration markers ───────────────────────────────────────────────


def test_loop_has_cache_crown_markers():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "cache-crown-import-d" in src, "cache-crown-import-d missing"
            assert "cache-crown-dispatch-d" in src, "cache-crown-dispatch-d missing"
            assert "cache-crown-doctrine-d" in src, "cache-crown-doctrine-d missing"
            return
        p = p.parent
    pytest.skip("loop.py not found")
