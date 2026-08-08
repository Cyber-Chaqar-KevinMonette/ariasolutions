"""Tests for memory_write — the generic Atom-write tool. Found live
2026-08-02: write_atom() alone never populated fts_atoms/vec_atoms, so
every atom ever written through this tool was permanently unsearchable
via memory_search. Fixed at the write_atom() level (memory/atom.py) for
FTS, plus an explicit vector-index step here for the async embedding call.
"""
from __future__ import annotations

import pytest

from sovereign_agent.tools.memory_write import MemoryWriteTool


@pytest.mark.asyncio
async def test_write_is_indexed_and_findable(tmp_path):
    """Real end-to-end: written atom must actually show up in a plain
    memory_search query — the whole point of writing it at all."""
    from sovereign_agent.tools.memory_search import MemorySearchTool

    tool = MemoryWriteTool()
    result = await tool.execute(
        tool.Args(
            type="observation",
            summary="the sprite QA gate rejects any generated image with no real alpha variance",
            content="rembg matting + a deterministic sanity check now run before a sprite reaches a scene file",
            parents=["evt_001"],
            confidence=0.9,
            scope_tags=["game-dev"],
        ),
        trace_id="t1",
    )
    assert result.ok, result.error
    assert result.output["atom_id"] is not None
    assert result.output["vector_indexed"] is True

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        fts_row = conn.execute(
            "SELECT summary FROM fts_atoms WHERE atom_id = ?", (result.output["atom_id"],)
        ).fetchone()
        vec_row = conn.execute(
            "SELECT atom_id FROM vec_atoms WHERE atom_id = ?", (result.output["atom_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert fts_row is not None
    assert vec_row is not None

    search = MemorySearchTool()
    search_result = await search.execute(
        search.Args(query="checking generated sprite images have real transparency before use", top_k=5),
        trace_id="t2",
    )
    assert search_result.ok, search_result.error
    summaries = [hit["summary"] for hit in search_result.output]
    assert result.output["atom_id"] in [
        hit["atom_id"] for hit in search_result.output
    ] or any("sprite QA gate" in s for s in summaries)
