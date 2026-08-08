"""
test_provenance_tool.py — Tests for trace_provenance tool (M23).
"""
from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "trace_provenance" in _TIER_REGISTRY
    assert _TIER_REGISTRY["trace_provenance"].tier == 0


def test_failure_modes():
    from sovereign_agent.tools.provenance_tool import TraceProvenanceTool
    assert TraceProvenanceTool.failure_modes


@pytest.mark.asyncio
async def test_node_not_found_returns_ok(tmp_path):
    """Node that doesn't exist returns ok=True with informative message."""
    from sovereign_agent.tools.provenance_tool import TraceProvenanceTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS atoms "
        "(atom_id TEXT PRIMARY KEY, parent_atom_id TEXT, parents TEXT)"
    )
    conn.commit()
    conn.close()

    def _open_atoms_db():
        return sqlite3.connect(str(db_path))

    with patch("sovereign_agent.tools.provenance_tool.open_atoms_db", _open_atoms_db):
        tool = TraceProvenanceTool()
        result = await tool.execute(
            tool.Args(node_id="nonexistent-node-id"),
            trace_id="t1",
        )

    assert result.ok
    assert "not exist" in result.output or result.metadata["nodes"] == 0


@pytest.mark.asyncio
async def test_tree_format_for_atom_with_parent(tmp_path):
    """Atom with a parent shows the supersedes chain in tree format."""
    from sovereign_agent.tools.provenance_tool import TraceProvenanceTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS atoms "
        "(atom_id TEXT PRIMARY KEY, parent_atom_id TEXT, parents TEXT)"
    )
    conn.execute("INSERT INTO atoms VALUES ('child-001', 'parent-001', '[]')")
    conn.execute("INSERT INTO atoms VALUES ('parent-001', NULL, '[]')")
    conn.commit()
    conn.close()

    def _open_atoms_db():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    with patch("sovereign_agent.tools.provenance_tool.open_atoms_db", _open_atoms_db):
        tool = TraceProvenanceTool()
        result = await tool.execute(
            tool.Args(node_id="child-001", depth=5, format="tree"),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "parent-001" in result.output
    assert "supersedes" in result.output


@pytest.mark.asyncio
async def test_json_format(tmp_path):
    """json format returns parseable dict."""
    import json
    from sovereign_agent.tools.provenance_tool import TraceProvenanceTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS atoms "
        "(atom_id TEXT PRIMARY KEY, parent_atom_id TEXT, parents TEXT)"
    )
    conn.execute("INSERT INTO atoms VALUES ('node-A', 'node-B', '[]')")
    conn.execute("INSERT INTO atoms VALUES ('node-B', NULL, '[]')")
    conn.commit()
    conn.close()

    def _open_atoms_db():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    with patch("sovereign_agent.tools.provenance_tool.open_atoms_db", _open_atoms_db):
        tool = TraceProvenanceTool()
        result = await tool.execute(
            tool.Args(node_id="node-A", depth=5, format="json"),
            trace_id="t1",
        )

    assert result.ok, result.error
    data = json.loads(result.output)
    assert "root" in data
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_summary_format(tmp_path):
    """summary format returns node/edge counts."""
    from sovereign_agent.tools.provenance_tool import TraceProvenanceTool

    db_path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS atoms "
        "(atom_id TEXT PRIMARY KEY, parent_atom_id TEXT, parents TEXT)"
    )
    conn.execute("INSERT INTO atoms VALUES ('x-001', 'x-002', '[]')")
    conn.execute("INSERT INTO atoms VALUES ('x-002', NULL, '[]')")
    conn.commit()
    conn.close()

    def _open_atoms_db():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    with patch("sovereign_agent.tools.provenance_tool.open_atoms_db", _open_atoms_db):
        tool = TraceProvenanceTool()
        result = await tool.execute(
            tool.Args(node_id="x-001", depth=5, format="summary"),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "nodes:" in result.output
    assert "edges:" in result.output


@pytest.mark.asyncio
async def test_invalid_format_rejected():
    """Unknown format returns ok=False."""
    from sovereign_agent.tools.provenance_tool import TraceProvenanceTool

    tool = TraceProvenanceTool()
    result = await tool.execute(
        tool.Args(node_id="some-id", format="xml"),
        trace_id="t1",
    )
    assert not result.ok
    assert "format" in result.error
