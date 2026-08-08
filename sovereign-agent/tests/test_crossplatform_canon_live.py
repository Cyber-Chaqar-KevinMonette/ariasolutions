"""Behavior tests for aria-crossplatform-canon, promoted to live tests/."""
from __future__ import annotations

from pathlib import Path

import pytest


def _canon_dir():
    import sovereign_agent

    return Path(sovereign_agent.__file__).parent / "knowledge" / "crossplatform"


def test_canon_files_present_and_dense():
    d = _canon_dir()
    for name in ("linux.md", "windows.md", "macos.md", "mobile.md",
                 "eternal_traps.md", "PLATFORM_STANDARDS.md"):
        p = d / name
        assert p.is_file(), name
        assert len(p.read_text(encoding="utf-8")) > 800, f"{name} too thin"


def test_tool_registered_t0():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY

    assert "platform_guide" in _TIER_REGISTRY
    assert _TIER_REGISTRY["platform_guide"].tier == 0


@pytest.mark.asyncio
async def test_topic_retrieval_picks_the_right_sections():
    from sovereign_agent.tools.platform_guide import PlatformGuideTool

    tool = PlatformGuideTool()
    r = await tool.execute(tool.Args(platform="windows", topic="service daemon lifecycle"),
                           trace_id="t")
    assert r.ok
    assert "Services" in r.output or "SCM" in r.output
    r2 = await tool.execute(tool.Args(platform="linux", topic="packaging deb rpm"),
                            trace_id="t")
    assert r2.ok and "deb" in r2.output


@pytest.mark.asyncio
async def test_aliases_and_unknown_platform():
    from sovereign_agent.tools.platform_guide import PlatformGuideTool

    tool = PlatformGuideTool()
    r = await tool.execute(tool.Args(platform="darwin", topic="signing"), trace_id="t")
    assert r.ok and ("notariz" in r.output.lower() or "sign" in r.output.lower())
    r2 = await tool.execute(tool.Args(platform="templeos"), trace_id="t")
    assert not r2.ok and "unknown_platform" in r2.error


@pytest.mark.asyncio
async def test_standards_checklist_reachable():
    from sovereign_agent.tools.platform_guide import PlatformGuideTool

    tool = PlatformGuideTool()
    r = await tool.execute(tool.Args(platform="standards"), trace_id="t")
    assert r.ok and "god-tier" in r.output


def test_canon_joins_her_training_corpus():
    from sovereign_agent.aria_lm.data import gather_corpus

    corpus = gather_corpus(max_chars=200_000, clean=False)
    assert "eternal traps" in corpus.lower() or "PLATFORM_STANDARDS" in corpus
