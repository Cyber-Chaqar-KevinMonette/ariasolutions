"""Tests for aria-people-health PH2: RecordHealthFactTool — real tool
machinery, a real (temp) atoms.db, no mocks on the write path itself."""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir.parent))
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()
    original = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield
    finally:
        object.__setattr__(SETTINGS, "paths", original)


def test_tool_metadata():
    from sovereign_agent.tools.health_record_tool import RecordHealthFactTool

    assert RecordHealthFactTool.tier == 3
    assert RecordHealthFactTool.requires_approval is True
    assert RecordHealthFactTool.failure_modes


def _migrate(conn) -> None:
    """Real installs run `sov migrate`/doctor to apply pending migrations
    (archive.py's table, among others) — open_atoms_db() alone only
    bootstraps 002_atoms.sql. Mirror that real precondition here rather
    than relying on incidental table absence/presence."""
    from pathlib import Path

    from sovereign_agent import migrations

    sql_dir = Path(migrations.__file__).parent.parent.parent / "sql"
    migrations.register_sql_dir(sql_dir)
    migrations.apply_pending(conn)


def test_tool_records_a_fact_for_the_principal():
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.mem_channels.people import PeopleChannel
    from sovereign_agent.tools.health_record_tool import (
        RecordHealthFactTool,
        _RecordHealthFactArgs,
    )

    conn = open_atoms_db()
    try:
        _migrate(conn)
        pc = PeopleChannel(conn)
        pc.upsert_person(canonical_name="Kevin", is_principal=True, idempotency_id="tool-mk1")
    finally:
        conn.close()

    tool = RecordHealthFactTool()
    args = _RecordHealthFactArgs(person_name="Kevin", kind="condition", value="seasonal allergies")
    result = asyncio.run(tool.execute(args, trace_id="tt-1"))
    assert result.ok, result.error
    assert result.output["person_name"] == "Kevin"
    assert result.output["status"] == "confirmed"


def test_tool_refuses_for_a_non_consented_person():
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.mem_channels.people import PeopleChannel
    from sovereign_agent.tools.health_record_tool import (
        RecordHealthFactTool,
        _RecordHealthFactArgs,
    )

    conn = open_atoms_db()
    try:
        _migrate(conn)
        pc = PeopleChannel(conn)
        pc.upsert_person(canonical_name="Kevin", is_principal=True, idempotency_id="tool-mk2")
        pc.upsert_person(canonical_name="Alex", idempotency_id="tool-mk3")
    finally:
        conn.close()

    tool = RecordHealthFactTool()
    args = _RecordHealthFactArgs(person_name="Alex", kind="condition", value="asthma")
    result = asyncio.run(tool.execute(args, trace_id="tt-2"))
    assert not result.ok
    assert "consent_required" in result.error


def test_tool_reports_unknown_person_honestly():
    from sovereign_agent.tools.health_record_tool import (
        RecordHealthFactTool,
        _RecordHealthFactArgs,
    )

    tool = RecordHealthFactTool()
    args = _RecordHealthFactArgs(person_name="Nobody Ever Mentioned", kind="note", value="x")
    result = asyncio.run(tool.execute(args, trace_id="tt-3"))
    assert not result.ok
    assert "person_not_found" in result.error
