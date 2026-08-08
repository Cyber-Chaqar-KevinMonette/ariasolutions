"""Tests for M59 — reflection-crown tools."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

CREATE_ATOMS = """\
CREATE TABLE IF NOT EXISTS atoms (
    atom_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    scope_path TEXT,
    scope_tags TEXT DEFAULT '[]',
    summary TEXT NOT NULL,
    content_ref TEXT DEFAULT '{}',
    claims TEXT DEFAULT '[]',
    parents TEXT DEFAULT '[]',
    version INTEGER DEFAULT 1,
    parent_atom_id TEXT,
    policy TEXT DEFAULT 'local_only',
    confidence REAL DEFAULT 0.5,
    created_at TEXT,
    created_by TEXT DEFAULT '{}',
    superseded_at TEXT,
    superseded_by TEXT
)
"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(CREATE_ATOMS)
    conn.commit()
    return path, conn


def _patch_db(db_path):
    return patch(
        "sovereign_agent.tools.reflection_tools.open_atoms_db",
        side_effect=lambda: sqlite3.connect(str(db_path), check_same_thread=False),
    )


def _insert_experience(conn, atom_id, summary, surprise_level=0.3):
    from datetime import datetime, timezone
    content = json.dumps({"content": json.dumps({
        "what_happened": summary,
        "surprise_level": surprise_level,
        "domain": "testing",
    })})
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, parents, created_at, created_by) "
        "VALUES (?, 'experience', ?, ?, '[]', ?, '{}')",
        (atom_id, summary, content, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()


def _insert_reflection(conn, atom_id, period, score, band="building"):
    from datetime import datetime, timezone
    content = json.dumps({"content": json.dumps({
        "period": period,
        "score": score,
        "score_band": band,
        "memorable_moment": f"notable event in {period}",
    })})
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, scope_tags, parents, created_at, created_by) "
        "VALUES (?, 'weekly-reflection', ?, ?, ?, '[]', ?, '{}')",
        (atom_id, f"[{period}] score={score}", content,
         json.dumps(["weekly-reflection", period]),
         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Test: WeeklyReflectionTool
# ---------------------------------------------------------------------------

class TestWeeklyReflectionTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.reflection_tools import WeeklyReflectionTool
        self.tool = WeeklyReflectionTool()

    def test_name(self):
        assert self.tool.name == "weekly_reflection"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_writes_weekly_reflection_atom(self, db):
        db_path, conn = db
        written = {}
        mock_conn = MagicMock()

        def _fake_write(c, atom):
            written["atom"] = atom
            return "atom-id-weekly"

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.reflection_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.reflection_tools._get_weekly_metrics", return_value={"score": 42, "band": "building", "hypothesis_confirm_rate": 0.5}),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t01")

        assert result.ok is True
        assert "atom" in written
        assert written["atom"].type == "weekly-reflection"

    @pytest.mark.asyncio
    async def test_atom_has_required_keys(self, db):
        db_path, conn = db
        written = {}

        def _fake_write(c, atom):
            written["atom"] = atom
            return "aid"

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.reflection_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.reflection_tools._get_weekly_metrics", return_value={"score": 55, "band": "strong", "hypothesis_confirm_rate": 0.6}),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t02")

        assert result.ok is True
        output = result.output
        assert "week" in output
        assert "score" in output
        assert "memorable_moment" in output
        assert "reflection" in output

    @pytest.mark.asyncio
    async def test_score_in_valid_range(self, db):
        db_path, conn = db

        def _fake_write(c, atom):
            return "aid"

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.reflection_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.reflection_tools._get_weekly_metrics", return_value={"score": 75, "band": "strong", "hypothesis_confirm_rate": 0.8}),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t03")

        assert result.ok is True
        assert 0 <= result.output["score"] <= 100

    @pytest.mark.asyncio
    async def test_high_surprise_experience_becomes_memorable(self, db):
        db_path, conn = db
        _insert_experience(conn, "exp-boring", "routine task", surprise_level=0.2)
        _insert_experience(conn, "exp-wow", "totally unexpected discovery", surprise_level=0.95)

        def _fake_write(c, atom):
            return "aid"

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.reflection_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.reflection_tools._get_weekly_metrics", return_value={"score": 30, "band": "building", "hypothesis_confirm_rate": 0.0}),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t04")

        assert result.ok is True
        assert "totally unexpected discovery" in result.output["memorable_moment"]

    @pytest.mark.asyncio
    async def test_db_unavailable_returns_error(self):
        with (
            patch("sovereign_agent.tools.reflection_tools.open_atoms_db", None),
            patch("sovereign_agent.tools.reflection_tools.Atom", None),
            patch("sovereign_agent.tools.reflection_tools.write_atom", None),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t05")
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_atom_scope_tags_correct(self, db):
        db_path, conn = db
        written = {}

        def _fake_write(c, atom):
            written["atom"] = atom
            return "aid"

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.reflection_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.reflection_tools._get_weekly_metrics", return_value={"score": 40, "band": "building", "hypothesis_confirm_rate": 0.0}),
        ):
            await self.tool.execute(self.tool.Args(), trace_id="t06")

        tags = written["atom"].scope_tags
        assert "weekly-reflection" in tags

    @pytest.mark.asyncio
    async def test_next_week_intention_carried(self, db):
        db_path, conn = db

        def _fake_write(c, atom):
            return "aid"

        intention = "focus on eval-crown improvements next week"
        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.reflection_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.reflection_tools._get_weekly_metrics", return_value={"score": 50, "band": "strong", "hypothesis_confirm_rate": 0.5}),
        ):
            result = await self.tool.execute(self.tool.Args(next_week_intention=intention), trace_id="t07")

        assert result.ok is True
        assert intention in result.output["reflection"]["next_week_intention"]


# ---------------------------------------------------------------------------
# Test: ReflectionHistoryTool
# ---------------------------------------------------------------------------

class TestReflectionHistoryTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.reflection_tools import ReflectionHistoryTool
        self.tool = ReflectionHistoryTool()

    def test_name(self):
        assert self.tool.name == "reflection_history"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_returns_trend_list(self, db):
        db_path, conn = db
        _insert_reflection(conn, "r1", "2026-W24", 60, "strong")
        _insert_reflection(conn, "r2", "2026-W25", 75, "strong")

        with _patch_db(db_path):
            result = await self.tool.execute(self.tool.Args(limit=5), trace_id="t08")

        assert result.ok is True
        assert result.output["count"] == 2
        for entry in result.output["trend"]:
            assert "period" in entry
            assert "score" in entry

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_trend(self, db):
        db_path, conn = db

        with _patch_db(db_path):
            result = await self.tool.execute(self.tool.Args(), trace_id="t09")

        assert result.ok is True
        assert result.output["count"] == 0
        assert result.output["trend"] == []

    @pytest.mark.asyncio
    async def test_cron_expression_valid(self):
        """Verify the weekly-reflection cron '5 9 * * 1' is valid."""
        from sovereign_agent.schedule import cron_matches
        from datetime import datetime, timezone
        dt = datetime(2026, 6, 22, 9, 5, tzinfo=timezone.utc)  # Monday 09:05
        assert cron_matches("5 9 * * 1", dt) is True
