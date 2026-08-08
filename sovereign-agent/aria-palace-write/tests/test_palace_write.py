"""
test_palace_write.py — Tests for palace write tools (M19).
"""
from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_tools_registered():
    """palace_write_room, palace_write_closet, palace_write_triple must be T1."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    for name in ("palace_write_room", "palace_write_closet", "palace_write_triple"):
        assert name in _TIER_REGISTRY, f"{name} not registered"
        assert _TIER_REGISTRY[name].tier == 1, f"{name} must be Tier 1"


def test_tools_have_failure_modes():
    from sovereign_agent.tools.palace_write import (
        PalaceWriteRoomTool, PalaceWriteClosetTool, PalaceWriteTripleTool,
    )
    assert PalaceWriteRoomTool.failure_modes
    assert PalaceWriteClosetTool.failure_modes
    assert PalaceWriteTripleTool.failure_modes


@pytest.mark.asyncio
async def test_write_room_creates_room(tmp_path):
    """palace_write_room creates a room and returns ok=True."""
    from sovereign_agent.tools.palace_write import PalaceWriteRoomTool

    db_path = tmp_path / "palace.db"

    def _open_palace():
        from sovereign_agent.palace import Palace
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteRoomTool()
        result = await tool.execute(
            tool.Args(name="Test Room", description="A test room"),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "room-test-room" in result.output or "created" in result.output
    assert result.metadata["existed"] is False

    # Verify in DB
    from sovereign_agent.palace import Palace
    palace = Palace(db_path)
    rooms = palace.list_rooms()
    palace.close()
    assert len(rooms) == 1
    assert rooms[0].name == "Test Room"


@pytest.mark.asyncio
async def test_write_room_idempotent(tmp_path):
    """Calling palace_write_room twice with same name returns ok=True both times."""
    from sovereign_agent.tools.palace_write import PalaceWriteRoomTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteRoomTool()
        r1 = await tool.execute(tool.Args(name="My Room"), trace_id="t1")
        r2 = await tool.execute(tool.Args(name="My Room"), trace_id="t2")

    assert r1.ok
    assert r2.ok
    assert r2.metadata["existed"] is True

    palace = Palace(db_path)
    assert len(palace.list_rooms()) == 1
    palace.close()


@pytest.mark.asyncio
async def test_write_closet_success(tmp_path):
    """palace_write_closet creates a closet in an existing room."""
    from sovereign_agent.tools.palace_write import PalaceWriteRoomTool, PalaceWriteClosetTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        room_tool = PalaceWriteRoomTool()
        await room_tool.execute(
            room_tool.Args(name="Projects", room_id="room-projects"),
            trace_id="t0",
        )

        closet_tool = PalaceWriteClosetTool()
        result = await closet_tool.execute(
            closet_tool.Args(
                room_id="room-projects",
                topic="Sovereign agent core architecture",
                entities=["Aria", "Kevin", "sovereign-agent"],
            ),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "closet-tool-" in result.output or "Closet written" in result.output

    palace = Palace(db_path)
    closets = palace.list_closets(room_id="room-projects")
    palace.close()
    assert len(closets) == 1
    assert "Sovereign agent" in closets[0].topic
    assert "Aria" in closets[0].entities


@pytest.mark.asyncio
async def test_write_closet_room_not_found(tmp_path):
    """palace_write_closet fails gracefully when room doesn't exist."""
    from sovereign_agent.tools.palace_write import PalaceWriteClosetTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteClosetTool()
        result = await tool.execute(
            tool.Args(room_id="room-nonexistent", topic="something"),
            trace_id="t1",
        )

    assert not result.ok
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_write_triple_entity_object(tmp_path):
    """palace_write_triple writes a triple with an entity object."""
    from sovereign_agent.tools.palace_write import PalaceWriteTripleTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteTripleTool()
        result = await tool.execute(
            tool.Args(
                subject="Aria",
                predicate="maintained_by",
                object_entity="Kevin",
                subject_type="agent",
                object_type="person",
                confidence=1.0,
            ),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "triple-" in result.output or "Triple written" in result.output
    assert result.metadata["predicate"] == "maintained_by"

    palace = Palace(db_path)
    subj_id = result.metadata["subject_id"]
    triples = palace.query_subject(subj_id)
    palace.close()
    assert len(triples) == 1
    assert triples[0].predicate == "maintained_by"
    assert triples[0].object_id is not None
    assert triples[0].object_literal is None


@pytest.mark.asyncio
async def test_write_triple_literal_object(tmp_path):
    """palace_write_triple writes a triple with a literal object."""
    from sovereign_agent.tools.palace_write import PalaceWriteTripleTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteTripleTool()
        result = await tool.execute(
            tool.Args(
                subject="Aria",
                predicate="kernel",
                object_literal="Safety·Love·Flourishing",
                confidence=1.0,
            ),
            trace_id="t1",
        )

    assert result.ok, result.error

    palace = Palace(db_path)
    subj_id = result.metadata["subject_id"]
    triples = palace.query_subject(subj_id)
    palace.close()
    assert len(triples) == 1
    assert triples[0].object_literal == "Safety·Love·Flourishing"
    assert triples[0].object_id is None


@pytest.mark.asyncio
async def test_write_triple_constraint_error(tmp_path):
    """Both or neither object_entity and object_literal returns ok=False."""
    from sovereign_agent.tools.palace_write import PalaceWriteTripleTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteTripleTool()

        # Both set
        r1 = await tool.execute(
            tool.Args(
                subject="X", predicate="p",
                object_entity="Y", object_literal="Z",
            ),
            trace_id="t1",
        )
        # Neither set
        r2 = await tool.execute(
            tool.Args(subject="X", predicate="p"),
            trace_id="t2",
        )

    assert not r1.ok
    assert not r2.ok


@pytest.mark.asyncio
async def test_write_triple_idempotent(tmp_path):
    """Same triple written twice stays as one row (INSERT OR REPLACE)."""
    from sovereign_agent.tools.palace_write import PalaceWriteTripleTool
    from sovereign_agent.palace import Palace

    db_path = tmp_path / "palace.db"

    def _open_palace():
        return Palace(db_path)

    with patch("sovereign_agent.tools.palace_write._open_palace", _open_palace):
        tool = PalaceWriteTripleTool()
        args = tool.Args(
            subject="Kevin", predicate="role", object_literal="maintainer",
        )
        r1 = await tool.execute(args, trace_id="t1")
        r2 = await tool.execute(args, trace_id="t2")

    assert r1.ok
    assert r2.ok
    assert r1.metadata["triple_id"] == r2.metadata["triple_id"]

    palace = Palace(db_path)
    subj_id = r1.metadata["subject_id"]
    triples = palace.query_subject(subj_id)
    palace.close()
    assert len(triples) == 1
