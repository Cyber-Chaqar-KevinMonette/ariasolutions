"""Tests for aria-business-playbook."""
from __future__ import annotations

import asyncio

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_package_imports():
    import sovereign_agent.business_playbook  # noqa: F401
    assert True


# ── content regression guard: the one thing Kevin was explicit about ──────


def test_no_religious_content_leaked():
    from sovereign_agent.business_playbook import PLAYBOOK

    blocked = ("creator", "pray", " god", "god.", "god,", "heavenly father", "amen", "scripture")
    for fw in PLAYBOOK:
        haystack = " ".join(fw.steps).lower() + " " + " ".join(fw.principles).lower() + " " + fw.name.lower()
        for term in blocked:
            assert term not in haystack, f"{fw.name!r} contains {term!r}"


def test_every_entry_has_honest_source():
    from sovereign_agent.business_playbook import PLAYBOOK, SOURCE_NOTE

    assert "Ryan Blair" in SOURCE_NOTE
    assert "religious content omitted" in SOURCE_NOTE
    for fw in PLAYBOOK:
        assert fw.source == SOURCE_NOTE


# ── find_frameworks() keyword routing ──────────────────────────────────────


def test_find_frameworks_negotiation():
    from sovereign_agent.business_playbook import find_frameworks

    matches = find_frameworks("negotiation")
    names = {fw.name for fw in matches}
    assert len(matches) == 3
    assert "Negotiation — Prep & Mindset" in names
    assert "Negotiation — Listening & Confirming" in names
    assert "Negotiation — Closing" in names


def test_find_frameworks_trust():
    from sovereign_agent.business_playbook import find_frameworks

    matches = find_frameworks("trust")
    assert any(fw.name == "The 5 Levels of Trust" for fw in matches)


def test_find_frameworks_hiring():
    from sovereign_agent.business_playbook import find_frameworks

    matches = find_frameworks("hiring")
    assert any(fw.name == "A-Player Profile (Hiring Rubric)" for fw in matches)


def test_find_frameworks_purpose():
    from sovereign_agent.business_playbook import find_frameworks

    matches = find_frameworks("purpose")
    assert any(fw.name == "Purpose Statement" for fw in matches)


def test_find_frameworks_no_match_returns_empty_list():
    from sovereign_agent.business_playbook import find_frameworks

    assert find_frameworks("xyzzy-nonexistent-topic") == []


def test_find_frameworks_category_browse_with_empty_query():
    from sovereign_agent.business_playbook import find_frameworks

    matches = find_frameworks("", category="negotiation")
    assert len(matches) == 3


def test_find_frameworks_rejects_unknown_category():
    from sovereign_agent.business_playbook import find_frameworks

    with pytest.raises(ValueError):
        find_frameworks("anything", category="not-a-real-category")


# ── BusinessPlaybookTool ────────────────────────────────────────────────────


def test_business_playbook_tool_registered():
    from sovereign_agent.tools.business_playbook_tools import BusinessPlaybookTool

    assert BusinessPlaybookTool.name == "business_playbook"
    assert BusinessPlaybookTool.tier == 0
    assert BusinessPlaybookTool.failure_modes


def test_business_playbook_tool_execute_match():
    from sovereign_agent.tools.business_playbook_tools import BusinessPlaybookTool

    tool = BusinessPlaybookTool()
    result = _run(tool.execute(tool.Args(query="negotiation"), trace_id="t1"))

    assert result.ok
    assert result.output["count"] == 3
    assert all("source" in fw for fw in result.output["frameworks"])


def test_business_playbook_tool_execute_no_match():
    from sovereign_agent.tools.business_playbook_tools import BusinessPlaybookTool

    tool = BusinessPlaybookTool()
    result = _run(tool.execute(tool.Args(query="xyzzy-nonexistent-topic"), trace_id="t1"))

    assert result.ok
    assert result.output["count"] == 0
    assert "note" in result.output


def test_business_playbook_tool_execute_unknown_category_is_graceful():
    from sovereign_agent.tools.business_playbook_tools import BusinessPlaybookTool

    tool = BusinessPlaybookTool()
    result = _run(tool.execute(tool.Args(query="x", category="not-a-real-category"), trace_id="t1"))

    assert not result.ok
    assert "read_error" in result.error
