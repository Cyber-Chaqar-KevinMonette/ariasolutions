"""Tests for aria-engineering-playbook."""
from __future__ import annotations

import asyncio

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_package_imports():
    import sovereign_agent.engineering_playbook  # noqa: F401
    assert True


def test_twelve_principles_present():
    from sovereign_agent.engineering_playbook import PRINCIPLES
    assert len(PRINCIPLES) == 12


# ── source-honesty: index, not reproduction ────────────────────────────────


def test_every_entry_names_its_real_skill_and_source():
    from sovereign_agent.engineering_playbook import PRINCIPLES, SOURCE_REPO

    assert "wondelai/skills" in SOURCE_REPO
    for p in PRINCIPLES:
        assert p.skill_slug in p.source
        assert "wondelai/skills" in p.source
        assert "index" in p.source.lower()
        assert p.skill_slug  # non-empty, real slug
        assert p.disciplines  # never an empty index entry


# ── find_principles() keyword routing ───────────────────────────────────────


def test_find_principles_circuit_breaker():
    from sovereign_agent.engineering_playbook import find_principles

    matches = find_principles("circuit breaker")
    assert any(p.skill_slug == "release-it" for p in matches)


def test_find_principles_bounded_context():
    from sovereign_agent.engineering_playbook import find_principles

    matches = find_principles("bounded context")
    assert any(p.skill_slug == "domain-driven-design" for p in matches)


def test_find_principles_by_slug():
    from sovereign_agent.engineering_playbook import find_principles

    matches = find_principles("clean-code")
    assert any(p.skill_slug == "clean-code" for p in matches)


def test_find_principles_no_match_returns_empty_list():
    from sovereign_agent.engineering_playbook import find_principles

    assert find_principles("xyzzy-nonexistent-topic") == []


def test_find_principles_category_browse_with_empty_query():
    from sovereign_agent.engineering_playbook import find_principles

    matches = find_principles("", category="systems-architecture")
    assert len(matches) == 6


def test_find_principles_rejects_unknown_category():
    from sovereign_agent.engineering_playbook import find_principles

    with pytest.raises(ValueError):
        find_principles("anything", category="not-a-real-category")


# ── EngineeringPlaybookTool ─────────────────────────────────────────────────


def test_engineering_playbook_tool_registered():
    from sovereign_agent.tools.engineering_playbook_tools import EngineeringPlaybookTool

    assert EngineeringPlaybookTool.name == "engineering_playbook"
    assert EngineeringPlaybookTool.tier == 0
    assert EngineeringPlaybookTool.failure_modes


def test_engineering_playbook_tool_execute_match():
    from sovereign_agent.tools.engineering_playbook_tools import EngineeringPlaybookTool

    tool = EngineeringPlaybookTool()
    result = _run(tool.execute(tool.Args(query="ddd"), trace_id="t1"))

    assert result.ok
    assert result.output["count"] >= 1
    assert all("source" in p for p in result.output["principles"])


def test_engineering_playbook_tool_execute_no_match():
    from sovereign_agent.tools.engineering_playbook_tools import EngineeringPlaybookTool

    tool = EngineeringPlaybookTool()
    result = _run(tool.execute(tool.Args(query="xyzzy-nonexistent-topic"), trace_id="t1"))

    assert result.ok
    assert result.output["count"] == 0
    assert "note" in result.output


def test_engineering_playbook_tool_execute_unknown_category_is_graceful():
    from sovereign_agent.tools.engineering_playbook_tools import EngineeringPlaybookTool

    tool = EngineeringPlaybookTool()
    result = _run(tool.execute(tool.Args(query="x", category="not-a-real-category"), trace_id="t1"))

    assert not result.ok
    assert "read_error" in result.error
