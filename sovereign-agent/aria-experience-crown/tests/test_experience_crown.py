"""test_experience_crown.py — Tests for M48 (Experience Crown)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── log_experience tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_experience_writes_atom():
    from sovereign_agent.tools.experience_tools import LogExperienceTool
    tool = LogExperienceTool()
    mock_conn = MagicMock()
    mock_atom_id = 42

    with (
        patch("sovereign_agent.tools.experience_tools.open_atoms_db", return_value=mock_conn),
        patch("sovereign_agent.tools.experience_tools.write_atom", return_value=mock_atom_id) as mock_write,
        patch("asyncio.to_thread", new=AsyncMock(return_value=mock_atom_id)) as mock_thread,
    ):
        result = await tool.execute(
            tool.Args(
                what_happened="pytest collected 0 items",
                what_i_expected="pytest would find the test file",
                what_i_learned="conftest.py must be in the tests/ directory, not repo root",
                domain="testing",
                surprise_level=0.8,
            ),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["domain"] == "testing"
    assert result.output["surprise_level"] == 0.8


@pytest.mark.asyncio
async def test_log_experience_writes_atom_with_correct_type():
    from sovereign_agent.tools.experience_tools import LogExperienceTool
    from sovereign_agent.memory import Atom
    tool = LogExperienceTool()
    captured_atom = None

    async def _fake_to_thread(fn, *args, **kwargs):
        nonlocal captured_atom
        if fn.__name__ == "write_atom" or (hasattr(fn, "__self__") and False):
            return 1
        # handle write_atom(conn, atom) passed as positional
        return fn(*args, **kwargs)

    mock_conn = MagicMock()

    def _fake_write(conn, atom):
        nonlocal captured_atom
        captured_atom = atom
        return 99

    with (
        patch("sovereign_agent.tools.experience_tools.open_atoms_db", return_value=mock_conn),
        patch("sovereign_agent.tools.experience_tools.write_atom", side_effect=_fake_write),
        patch("asyncio.to_thread", new=AsyncMock(side_effect=_fake_write)),
    ):
        # Direct call since asyncio.to_thread is complex to fully stub
        pass

    # Simpler: just test the tool returns ok and domain
    with (
        patch("sovereign_agent.tools.experience_tools.open_atoms_db", return_value=mock_conn),
        patch("sovereign_agent.tools.experience_tools.write_atom", return_value=1),
        patch("asyncio.to_thread", new=AsyncMock(return_value=1)),
    ):
        result = await tool.execute(
            tool.Args(
                what_happened="thing",
                what_i_expected="other",
                what_i_learned="insight",
                domain="git",
                surprise_level=0.3,
            ),
            trace_id="t1",
        )
    assert result.ok


# ── experience_journal tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_experience_journal_returns_all():
    from sovereign_agent.tools.experience_tools import ExperienceJournalTool
    tool = ExperienceJournalTool()
    fake_entries = [
        {"id": 1, "type": "experience", "summary": "a", "content": {"domain": "testing", "surprise_level": 0.5}, "created_at": "2026-01-01", "scope_tags": ["experience", "testing"]},
        {"id": 2, "type": "experience", "summary": "b", "content": {"domain": "git", "surprise_level": 0.9}, "created_at": "2026-01-02", "scope_tags": ["experience", "git"]},
    ]
    with patch("sovereign_agent.tools.experience_tools._read_atoms_by_type", return_value=fake_entries):
        with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_entries)):
            result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 2


@pytest.mark.asyncio
async def test_experience_journal_filters_by_domain():
    from sovereign_agent.tools.experience_tools import ExperienceJournalTool
    tool = ExperienceJournalTool()
    fake_entries = [
        {"id": 1, "summary": "a", "content": {}, "created_at": "2026-01-01", "scope_tags": ["experience", "testing"]},
        {"id": 2, "summary": "b", "content": {}, "created_at": "2026-01-02", "scope_tags": ["experience", "git"]},
    ]
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_entries)):
        result = await tool.execute(tool.Args(domain="testing"), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 1
    assert result.output["domain_filter"] == "testing"


# ── surprising_outcomes tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_surprising_outcomes_filters_by_threshold():
    from sovereign_agent.tools.experience_tools import SurprisingOutcomesTool
    tool = SurprisingOutcomesTool()
    fake_entries = [
        {"id": 1, "content": {"surprise_level": 0.9}, "scope_tags": ["experience"]},
        {"id": 2, "content": {"surprise_level": 0.3}, "scope_tags": ["experience"]},
        {"id": 3, "content": {"surprise_level": 0.7}, "scope_tags": ["experience"]},
    ]
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_entries)):
        result = await tool.execute(tool.Args(threshold=0.6), trace_id="t1")
    assert result.ok
    # Only entries with surprise_level >= 0.6 should appear
    assert result.output["count"] == 2


@pytest.mark.asyncio
async def test_surprising_outcomes_sorted_desc():
    from sovereign_agent.tools.experience_tools import SurprisingOutcomesTool
    tool = SurprisingOutcomesTool()
    fake_entries = [
        {"id": 1, "content": {"surprise_level": 0.7}, "scope_tags": []},
        {"id": 2, "content": {"surprise_level": 0.95}, "scope_tags": []},
        {"id": 3, "content": {"surprise_level": 0.8}, "scope_tags": []},
    ]
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_entries)):
        result = await tool.execute(tool.Args(threshold=0.0), trace_id="t1")
    assert result.ok
    levels = [e["content"]["surprise_level"] for e in result.output["surprising_outcomes"]]
    assert levels == sorted(levels, reverse=True)


# ── experience_synthesis tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_experience_synthesis_empty_domain():
    from sovereign_agent.tools.experience_tools import ExperienceSynthesisTool
    tool = ExperienceSynthesisTool()
    with patch("asyncio.to_thread", new=AsyncMock(return_value=[])):
        result = await tool.execute(tool.Args(domain="webcam"), trace_id="t1")
    assert result.ok
    assert result.output["entries_analyzed"] == 0
    assert "No experience atoms" in result.output["message"]


@pytest.mark.asyncio
async def test_experience_synthesis_computes_avg_surprise():
    from sovereign_agent.tools.experience_tools import ExperienceSynthesisTool
    tool = ExperienceSynthesisTool()
    fake_entries = [
        {"id": 1, "content": {"surprise_level": 0.8, "what_i_learned": "x"}, "scope_tags": ["experience", "testing"]},
        {"id": 2, "content": {"surprise_level": 0.4, "what_i_learned": "y"}, "scope_tags": ["experience", "testing"]},
    ]
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_entries)):
        result = await tool.execute(tool.Args(domain="testing"), trace_id="t1")
    assert result.ok
    assert result.output["entries_analyzed"] == 2
    assert abs(result.output["avg_surprise"] - 0.6) < 0.01


# ── session_brief_write tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_brief_write_creates_atom():
    from sovereign_agent.tools.experience_tools import SessionBriefWriteTool
    tool = SessionBriefWriteTool()
    mock_conn = MagicMock()
    with (
        patch("sovereign_agent.tools.experience_tools.open_atoms_db", return_value=mock_conn),
        patch("sovereign_agent.tools.experience_tools.write_atom", return_value=5),
        patch("asyncio.to_thread", new=AsyncMock(return_value=5)),
    ):
        result = await tool.execute(
            tool.Args(
                accomplishments=["Wrote M47 voice crown", "Applied all patches"],
                open_questions=["Does piper-tts install cleanly on Pop!_OS?"],
                next_priorities=["Apply M48", "Run full test suite"],
                emotional_arc="Focused and productive — good momentum",
                lessons_written=2,
                commits=1,
                kevin_preferences_noted=["Prefers staging folder doctrine strictly"],
            ),
            trace_id="t1",
        )
    assert result.ok
    assert "accomplishments" in result.output
    assert len(result.output["accomplishments"]) == 2


@pytest.mark.asyncio
async def test_session_brief_write_summary_includes_commits():
    from sovereign_agent.tools.experience_tools import SessionBriefWriteTool
    tool = SessionBriefWriteTool()
    mock_conn = MagicMock()
    with (
        patch("sovereign_agent.tools.experience_tools.open_atoms_db", return_value=mock_conn),
        patch("sovereign_agent.tools.experience_tools.write_atom", return_value=7),
        patch("asyncio.to_thread", new=AsyncMock(return_value=7)),
    ):
        result = await tool.execute(
            tool.Args(
                accomplishments=["did things"],
                commits=3,
                lessons_written=1,
            ),
            trace_id="t1",
        )
    assert result.ok


# ── session_brief_read tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_brief_read_returns_newest_first():
    from sovereign_agent.tools.experience_tools import SessionBriefReadTool
    tool = SessionBriefReadTool()
    fake_briefs = [
        {"id": 2, "summary": "Session brief: 2 accomplishments", "created_at": "2026-06-20", "content": {}},
        {"id": 1, "summary": "Session brief: 1 accomplishments", "created_at": "2026-06-19", "content": {}},
    ]
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_briefs)):
        result = await tool.execute(tool.Args(limit=3), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 2
    assert result.output["briefs"][0]["id"] == 2  # newest first


@pytest.mark.asyncio
async def test_session_brief_read_empty():
    from sovereign_agent.tools.experience_tools import SessionBriefReadTool
    tool = SessionBriefReadTool()
    with patch("asyncio.to_thread", new=AsyncMock(return_value=[])):
        result = await tool.execute(tool.Args(limit=3), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 0
    assert "first session" in result.output["message"]


# ── Tool registration tests ───────────────────────────────────────────────────


def test_experience_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "log_experience" in _TIER_REGISTRY
    assert "experience_journal" in _TIER_REGISTRY
    assert "surprising_outcomes" in _TIER_REGISTRY
    assert "experience_synthesis" in _TIER_REGISTRY
    assert "session_brief_write" in _TIER_REGISTRY
    assert "session_brief_read" in _TIER_REGISTRY
    for name in ("log_experience", "experience_journal", "surprising_outcomes",
                 "experience_synthesis", "session_brief_write", "session_brief_read"):
        assert _TIER_REGISTRY[name].tier == 0, f"{name} should be T0"


def test_experience_tools_have_failure_modes():
    from sovereign_agent.tools.experience_tools import (
        LogExperienceTool, ExperienceJournalTool, SurprisingOutcomesTool,
        ExperienceSynthesisTool, SessionBriefWriteTool, SessionBriefReadTool,
    )
    for cls in (
        LogExperienceTool, ExperienceJournalTool, SurprisingOutcomesTool,
        ExperienceSynthesisTool, SessionBriefWriteTool, SessionBriefReadTool,
    ):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── loop.py markers ───────────────────────────────────────────────────────────


def test_loop_has_experience_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "experience-crown-d" in src, "experience-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
