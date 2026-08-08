"""Tests for M58 — hypothesis-close tools."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# DB fixture with schema
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
    conn = sqlite3.connect(str(path))
    conn.execute(CREATE_ATOMS)
    conn.commit()
    return path, conn


def _insert_hypothesis(conn, atom_id, question, days_ago=1, value=0.7, cost="medium"):
    from datetime import datetime, timezone, timedelta
    created = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = json.dumps({"content": json.dumps({
        "hypothesis": f"If context, then {question}",
        "null_hypothesis": f"No change for {question}",
        "value_if_confirmed": value,
        "estimated_test_cost": cost,
        "status": "pending",
    })})
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, parents, created_at, created_by) "
        "VALUES (?, 'hypothesis', ?, ?, '[]', ?, '{}')",
        (atom_id, f"[{cost}/{value}] {question}", content, created),
    )
    conn.commit()


def _insert_result(conn, atom_id, hypothesis_id, verdict, lesson="lesson text"):
    from datetime import datetime, timezone
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = json.dumps({"content": json.dumps({
        "hypothesis_id": hypothesis_id,
        "verdict": verdict,
        "lesson": lesson,
        "new_confidence": 0.8 if verdict == "confirmed" else 0.2,
    })})
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, parents, created_at, created_by) "
        "VALUES (?, 'hypothesis-result', ?, ?, '[]', ?, '{}')",
        (atom_id, f"[{verdict}] {lesson[:50]}", content, created),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Test: HypothesisQueueTool
# ---------------------------------------------------------------------------

class TestHypothesisQueueTool:
    @pytest.fixture(autouse=True)
    def _setup(self, db):
        from sovereign_agent.tools.hypothesis_close import HypothesisQueueTool
        self.tool = HypothesisQueueTool()
        self.db_path, self.conn = db

    def _patch(self):
        path = str(self.db_path)
        return patch(
            "sovereign_agent.tools.hypothesis_close.open_atoms_db",
            side_effect=lambda: sqlite3.connect(path, check_same_thread=False),
        )

    def test_name(self):
        assert self.tool.name == "hypothesis_queue"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_returns_only_open_by_default(self):
        _insert_hypothesis(self.conn, "hyp-1", "will it work?", days_ago=5)
        _insert_hypothesis(self.conn, "hyp-2", "will it fail?", days_ago=3)
        _insert_result(self.conn, "res-1", "hyp-1", "confirmed")

        with self._patch():
            result = await self.tool.execute(self.tool.Args(), trace_id="t01")

        assert result.ok is True
        open_ids = [h["atom_id"] for h in result.output["open"]]
        assert "hyp-1" not in open_ids
        assert "hyp-2" in open_ids

    @pytest.mark.asyncio
    async def test_excludes_evaluated_from_open(self):
        _insert_hypothesis(self.conn, "hyp-a", "question a", days_ago=10)
        _insert_result(self.conn, "res-a", "hyp-a", "refuted")

        with self._patch():
            result = await self.tool.execute(self.tool.Args(), trace_id="t02")

        assert result.ok is True
        assert result.output["open_count"] == 0
        assert result.output["evaluated_count"] == 1

    @pytest.mark.asyncio
    async def test_sorted_oldest_first(self):
        _insert_hypothesis(self.conn, "old", "old question", days_ago=10)
        _insert_hypothesis(self.conn, "new", "new question", days_ago=1)

        with self._patch():
            result = await self.tool.execute(self.tool.Args(), trace_id="t03")

        assert result.ok is True
        ids = [h["atom_id"] for h in result.output["open"]]
        assert ids.index("old") < ids.index("new")

    @pytest.mark.asyncio
    async def test_db_unavailable_returns_empty(self):
        with patch("sovereign_agent.tools.hypothesis_close.open_atoms_db", None):
            result = await self.tool.execute(self.tool.Args(), trace_id="t04")
        assert result.ok is True
        assert result.output["open_count"] == 0


# ---------------------------------------------------------------------------
# Test: HypothesisSynthesisTool
# ---------------------------------------------------------------------------

class TestHypothesisSynthesisTool:
    @pytest.fixture(autouse=True)
    def _setup(self, db):
        from sovereign_agent.tools.hypothesis_close import HypothesisSynthesisTool
        self.tool = HypothesisSynthesisTool()
        self.db_path, self.conn = db

    def _patch(self):
        path = str(self.db_path)
        return patch(
            "sovereign_agent.tools.hypothesis_close.open_atoms_db",
            side_effect=lambda: sqlite3.connect(path, check_same_thread=False),
        )

    def test_name(self):
        assert self.tool.name == "hypothesis_synthesis"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_rate(self):
        with self._patch():
            result = await self.tool.execute(self.tool.Args(), trace_id="t05")

        assert result.ok is True
        assert result.output["confirm_rate"] == 0.0
        assert result.output["total_evaluated"] == 0

    @pytest.mark.asyncio
    async def test_counts_correctly(self):
        _insert_result(self.conn, "r1", "h1", "confirmed", lesson="lesson 1")
        _insert_result(self.conn, "r2", "h2", "confirmed", lesson="lesson 2")
        _insert_result(self.conn, "r3", "h3", "refuted", lesson="lesson 3")

        with self._patch():
            result = await self.tool.execute(self.tool.Args(days=30), trace_id="t06")

        assert result.ok is True
        assert result.output["total_evaluated"] == 3
        assert result.output["confirmed_count"] == 2
        assert result.output["refuted_count"] == 1
        assert abs(result.output["confirm_rate"] - 2/3) < 0.01

    @pytest.mark.asyncio
    async def test_domain_filter(self):
        _insert_result(self.conn, "r1", "h1", "confirmed", lesson="testing domain lesson")
        _insert_result(self.conn, "r2", "h2", "confirmed", lesson="git domain lesson")

        with self._patch():
            result = await self.tool.execute(self.tool.Args(days=30, domain_filter="git"), trace_id="t07")

        assert result.ok is True
        assert result.output["total_evaluated"] == 1
        assert result.output["confirmed_count"] == 1


# ---------------------------------------------------------------------------
# Test: HypothesisArchiveTool
# ---------------------------------------------------------------------------

class TestHypothesisArchiveTool:
    @pytest.fixture(autouse=True)
    def _setup(self, db):
        from sovereign_agent.tools.hypothesis_close import HypothesisArchiveTool
        self.tool = HypothesisArchiveTool()
        self.db_path, self.conn = db

    def _patch(self):
        path = str(self.db_path)
        return patch(
            "sovereign_agent.tools.hypothesis_close.open_atoms_db",
            side_effect=lambda: sqlite3.connect(path, check_same_thread=False),
        )

    def test_name(self):
        assert self.tool.name == "hypothesis_archive"

    def test_tier_is_1(self):
        assert self.tool.tier == 1

    @pytest.mark.asyncio
    async def test_archive_marks_superseded(self):
        _insert_hypothesis(self.conn, "stale-1", "stale question", days_ago=70)

        with self._patch():
            result = await self.tool.execute(
                self.tool.Args(hypothesis_id="stale-1", reason="stale"),
                trace_id="t08",
            )

        assert result.ok is True
        row = self.conn.execute(
            "SELECT superseded_at, superseded_by FROM atoms WHERE atom_id = 'stale-1'"
        ).fetchone()
        assert row is not None
        assert row[0] is not None  # superseded_at set
        assert "archived-stale" in row[1]

    @pytest.mark.asyncio
    async def test_archive_missing_hypothesis_returns_error(self):
        with self._patch():
            result = await self.tool.execute(
                self.tool.Args(hypothesis_id="nonexistent-id"),
                trace_id="t09",
            )

        assert result.ok is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_archive_db_unavailable_returns_error(self):
        with patch("sovereign_agent.tools.hypothesis_close.open_atoms_db", None):
            result = await self.tool.execute(
                self.tool.Args(hypothesis_id="any-id"),
                trace_id="t10",
            )
        assert result.ok is False
        assert "unavailable" in result.error.lower()
