"""Tests for record_game_lesson — durable, cross-project game-dev memory."""
from __future__ import annotations

import pytest

from sovereign_agent import game_dev_xp
from sovereign_agent.game_projects import GameProject, save
from sovereign_agent.tools.record_game_lesson import RecordGameLessonTool

_LESSON_KW = dict(
    trigger="place_game_sprite wired an ungenerated grid image straight into the scene",
    context="generating a first sprite for Ember Keep with sdxl-turbo",
    failure_mode="text-to-image diffusion has no concept of alpha; output was an opaque white-background contact sheet",
    correction="ran the output through rembg for real matting before ever touching the scene file",
    rule="always background-remove + sanity-check generated sprites before wiring them into a scene",
    confidence=0.9,
)


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = RecordGameLessonTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost", **_LESSON_KW), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_lesson_recorded_to_local_xp_ledger(tmp_path):
    save(GameProject(project_name="Ember Keep", genre="idle-incremental", engine="godot"), tmp_path)
    tool = RecordGameLessonTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ember-keep", **_LESSON_KW), trace_id="t1")

    assert result.ok, result.error
    events = game_dev_xp.recent_events(10, "ember-keep", tmp_path)
    assert len(events) == 1
    assert events[0].event_type == "lesson_logged"
    assert "background-remove" in events[0].note
    assert "confidence=0.90" in events[0].note


@pytest.mark.asyncio
async def test_lesson_recorded_to_atoms_db_with_scope_tags(tmp_path):
    from sovereign_agent.db import open_atoms_db
    # conftest.py's autouse isolate_paths fixture already redirects
    # SETTINGS.paths (and therefore atoms_db) into a per-test tmp dir —
    # no manual patching needed, this never touches the real production DB.

    save(GameProject(project_name="Ember Keep", genre="idle-incremental", engine="godot"), tmp_path)
    tool = RecordGameLessonTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ember-keep", **_LESSON_KW), trace_id="trace-xyz")

    assert result.ok, result.error
    assert result.output["atom_id"] is not None
    assert result.output["scope_tags"] == ["game-dev", "idle-incremental", "godot", "ember-keep"]

    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT type, scope_tags, parents, confidence, summary FROM atoms WHERE atom_id = ?",
            (result.output["atom_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    row_type, scope_tags_json, parents_json, confidence, summary = row
    assert row_type == "game_lesson"
    assert "idle-incremental" in scope_tags_json
    assert "trace-xyz" in parents_json
    assert confidence == 0.9
    assert summary == _LESSON_KW["rule"]

    # The actual bug this session found: write_atom() alone never
    # populated either search index, so the atom was permanently
    # unsearchable via memory_search regardless of the row existing.
    assert result.output["vector_indexed"] is True
    conn = open_atoms_db()
    try:
        fts_row = conn.execute(
            "SELECT summary FROM fts_atoms WHERE atom_id = ?", (result.output["atom_id"],),
        ).fetchone()
        vec_row = conn.execute(
            "SELECT atom_id FROM vec_atoms WHERE atom_id = ?", (result.output["atom_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert fts_row is not None
    assert vec_row is not None


@pytest.mark.asyncio
async def test_lesson_is_actually_findable_via_memory_search(tmp_path):
    """The real end-to-end proof: a lesson recorded here must be
    retrievable by a plain semantic query, the way a FUTURE, different
    game project's session would actually look it up."""
    from sovereign_agent.tools.memory_search import MemorySearchTool

    save(GameProject(project_name="Ember Keep", genre="idle-incremental", engine="godot"), tmp_path)
    tool = RecordGameLessonTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ember-keep", **_LESSON_KW), trace_id="t1")
    assert result.ok, result.error

    search = MemorySearchTool()
    search_result = await search.execute(
        search.Args(query="wiring a generated sprite image into a game scene safely", top_k=5),
        trace_id="t2",
    )
    assert search_result.ok, search_result.error
    summaries = [hit["summary"] for hit in search_result.output]
    assert _LESSON_KW["rule"] in summaries


@pytest.mark.asyncio
async def test_lesson_still_recorded_locally_if_atoms_db_layer_missing(tmp_path, monkeypatch):
    import sovereign_agent.tools.record_game_lesson as mod

    save(GameProject(project_name="Ember Keep", genre="idle-incremental", engine="godot"), tmp_path)
    monkeypatch.setattr(mod, "Atom", None)
    monkeypatch.setattr(mod, "open_atoms_db", None)

    tool = RecordGameLessonTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ember-keep", **_LESSON_KW), trace_id="t1")

    assert result.ok, result.error
    assert result.output["atom_id"] is None
    assert "XP ledger only" in result.output["message"]
    events = game_dev_xp.recent_events(10, "ember-keep", tmp_path)
    assert len(events) == 1
