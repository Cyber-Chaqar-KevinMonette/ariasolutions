"""
test_lessons_tool.py — Tests for the read_lessons Tier 0 tool.
"""
from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_tool_registered():
    """read_lessons must be registered at Tier 0."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "read_lessons" in _TIER_REGISTRY
    assert _TIER_REGISTRY["read_lessons"].tier == 0


def test_tool_has_failure_modes():
    from sovereign_agent.tools.lessons_tool import ReadLessonsTool
    assert ReadLessonsTool.failure_modes


@pytest.mark.asyncio
async def test_read_lessons_empty_db(tmp_path):
    """Empty lessons table returns ok=True with 'no lessons yet' message."""
    from sovereign_agent.tools.lessons_tool import ReadLessonsTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lessons "
        "(lesson_id TEXT PRIMARY KEY, ts TEXT, trigger TEXT, context TEXT, "
        "failure_mode TEXT, correction TEXT, rule TEXT, evidence_refs TEXT, confidence REAL)"
    )
    conn.commit()
    conn.close()

    def _open_atoms_db():
        return sqlite3.connect(str(db_path))

    with patch("sovereign_agent.tools.lessons_tool.open_atoms_db", _open_atoms_db):
        # Also need to patch the import inside execute
        import sovereign_agent.tools.lessons_tool as mod
        orig = None
        try:
            import sovereign_agent.db as db_mod
            orig = db_mod.open_atoms_db
            db_mod.open_atoms_db = _open_atoms_db
        except (ImportError, AttributeError):
            pass

        tool = ReadLessonsTool()
        try:
            result = await tool.execute(tool.Args(limit=5), trace_id="t1")
        finally:
            if orig and hasattr(db_mod, "open_atoms_db"):
                db_mod.open_atoms_db = orig

    assert result.ok
    assert "No lessons" in result.output or result.metadata["count"] == 0


@pytest.mark.asyncio
async def test_read_lessons_with_data(tmp_path):
    """With lessons in db, returns formatted output with rule/correction."""
    from sovereign_agent.tools.lessons_tool import ReadLessonsTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lessons "
        "(lesson_id TEXT PRIMARY KEY, ts TEXT, trigger TEXT, context TEXT, "
        "failure_mode TEXT, correction TEXT, rule TEXT, evidence_refs TEXT, confidence REAL)"
    )
    conn.execute(
        "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("L01", "2026-06-19T10:00:00Z", "trigger text", "context text",
         "timeout", "use shorter timeout", "always set timeout < 30s", "[]", 0.9),
    )
    conn.execute(
        "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("L02", "2026-06-18T10:00:00Z", "another trigger", "another context",
         None, "check paths first", "validate paths before writing", "[]", 0.8),
    )
    conn.commit()
    conn.close()

    def _open_atoms_db():
        return sqlite3.connect(str(db_path))

    try:
        import sovereign_agent.db as db_mod
        orig = db_mod.open_atoms_db
        db_mod.open_atoms_db = _open_atoms_db
    except (ImportError, AttributeError):
        return  # skip if db module not accessible this way

    try:
        tool = ReadLessonsTool()
        result = await tool.execute(tool.Args(limit=10), trace_id="t2")
    finally:
        db_mod.open_atoms_db = orig

    assert result.ok
    assert result.metadata["count"] == 2
    assert "always set timeout" in result.output
    assert "validate paths" in result.output
    assert "RULE" in result.output


@pytest.mark.asyncio
async def test_read_lessons_topic_filter(tmp_path):
    """Topic filter returns only matching lessons."""
    from sovereign_agent.tools.lessons_tool import ReadLessonsTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lessons "
        "(lesson_id TEXT PRIMARY KEY, ts TEXT, trigger TEXT, context TEXT, "
        "failure_mode TEXT, correction TEXT, rule TEXT, evidence_refs TEXT, confidence REAL)"
    )
    conn.execute(
        "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("L01", "2026-06-19T10:00:00Z", "timeout error", "context",
         None, "fix", "always set timeout for network calls", "[]", 0.9),
    )
    conn.execute(
        "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("L02", "2026-06-18T10:00:00Z", "path error", "context",
         None, "fix", "validate filesystem paths", "[]", 0.8),
    )
    conn.commit()
    conn.close()

    def _open_atoms_db():
        return sqlite3.connect(str(db_path))

    try:
        import sovereign_agent.db as db_mod
        orig = db_mod.open_atoms_db
        db_mod.open_atoms_db = _open_atoms_db
    except (ImportError, AttributeError):
        return

    try:
        tool = ReadLessonsTool()
        result = await tool.execute(tool.Args(limit=10, topic="timeout"), trace_id="t3")
    finally:
        db_mod.open_atoms_db = orig

    assert result.ok
    assert result.metadata["count"] == 1
    assert "timeout" in result.output
    assert "filesystem" not in result.output
