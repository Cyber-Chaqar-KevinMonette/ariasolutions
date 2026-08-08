"""Tests for M61 — git-experience tools."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

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
        "sovereign_agent.tools.git_reflect.open_atoms_db",
        side_effect=lambda: sqlite3.connect(str(db_path), check_same_thread=False),
    )


def _fake_write(conn, atom):
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, scope_tags, parents, created_at, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), '{}')",
        (
            atom.atom_id,
            atom.type,
            atom.summary,
            json.dumps(atom.content_ref),
            json.dumps(atom.scope_tags),
            json.dumps(atom.parents),
        ),
    )
    return atom.atom_id


# ---------------------------------------------------------------------------
# Test: GitCommitReflectTool
# ---------------------------------------------------------------------------

class TestGitCommitReflectTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.git_reflect import GitCommitReflectTool
        self.tool = GitCommitReflectTool()

    def test_name(self):
        assert self.tool.name == "git_commit_reflect"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_writes_experience_atom(self, db):
        db_path, conn = db
        written = {}

        def _capture(c, atom):
            written["atom"] = atom
            return _fake_write(c, atom)

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect.write_atom", side_effect=_capture),
        ):
            result = await self.tool.execute(
                self.tool.Args(
                    commit_sha="abc12345",
                    what_changed="Added atoms compact sentinel",
                    why_it_mattered="Closes RISK-008 — unbounded store growth now monitored",
                ),
                trace_id="t01",
            )

        assert result.ok is True
        assert "atom" in written
        assert written["atom"].type == "experience"

    @pytest.mark.asyncio
    async def test_domain_is_git(self, db):
        db_path, conn = db
        written = {}

        def _capture(c, atom):
            written["atom"] = atom
            return _fake_write(c, atom)

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect.write_atom", side_effect=_capture),
        ):
            await self.tool.execute(
                self.tool.Args(
                    commit_sha="def67890",
                    what_changed="Test file",
                    why_it_mattered="Testing the reflection tool",
                ),
                trace_id="t02",
            )

        content = json.loads(written["atom"].content_ref["content"])
        assert content["domain"] == "git"

    @pytest.mark.asyncio
    async def test_scope_tags_include_sha_prefix(self, db):
        db_path, conn = db
        written = {}

        def _capture(c, atom):
            written["atom"] = atom
            return _fake_write(c, atom)

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect.write_atom", side_effect=_capture),
        ):
            await self.tool.execute(
                self.tool.Args(
                    commit_sha="feedbeef1234",
                    what_changed="some change",
                    why_it_mattered="important reason",
                ),
                trace_id="t03",
            )

        assert "feedbeef" in written["atom"].scope_tags
        assert "git" in written["atom"].scope_tags
        assert "commit" in written["atom"].scope_tags

    @pytest.mark.asyncio
    async def test_idempotent_same_sha(self, db):
        db_path, conn = db
        write_calls = []

        def _capture(c, atom):
            write_calls.append(atom)
            return _fake_write(c, atom)

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect.write_atom", side_effect=_capture),
        ):
            # First call
            r1 = await self.tool.execute(
                self.tool.Args(commit_sha="aabbccdd", what_changed="x", why_it_mattered="y"),
                trace_id="t04a",
            )
            # Second call with same sha
            r2 = await self.tool.execute(
                self.tool.Args(commit_sha="aabbccdd", what_changed="x", why_it_mattered="y"),
                trace_id="t04b",
            )

        assert r1.ok is True
        assert r1.output["idempotent"] is False
        assert r2.ok is True
        assert r2.output["idempotent"] is True
        assert len(write_calls) == 1  # only written once

    @pytest.mark.asyncio
    async def test_parents_non_empty(self, db):
        db_path, conn = db
        written = {}

        def _capture(c, atom):
            written["atom"] = atom
            return _fake_write(c, atom)

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect.write_atom", side_effect=_capture),
        ):
            await self.tool.execute(
                self.tool.Args(commit_sha="11223344", what_changed="stuff", why_it_mattered="growth"),
                trace_id="trace-non-empty",
            )

        assert written["atom"].parents == ["trace-non-empty"]

    @pytest.mark.asyncio
    async def test_db_unavailable_returns_error(self):
        with (
            patch("sovereign_agent.tools.git_reflect.open_atoms_db", None),
            patch("sovereign_agent.tools.git_reflect.Atom", None),
            patch("sovereign_agent.tools.git_reflect.write_atom", None),
        ):
            result = await self.tool.execute(
                self.tool.Args(commit_sha="deadbeef", what_changed="x", why_it_mattered="y"),
                trace_id="t06",
            )
        assert result.ok is False


# ---------------------------------------------------------------------------
# Test: GitWeekSummaryTool
# ---------------------------------------------------------------------------

class TestGitWeekSummaryTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.git_reflect import GitWeekSummaryTool
        self.tool = GitWeekSummaryTool()

    def test_name(self):
        assert self.tool.name == "git_week_summary"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_coverage_rate_correct(self, db):
        db_path, conn = db
        # 3 commits, 2 have reflections
        commits = ["abc12345", "def67890", "ghi11111"]
        reflected_shas = {"abc12345", "def67890"}

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect._git_commits_last_7_days", return_value=commits),
            patch("sovereign_agent.tools.git_reflect._git_reflect_atoms", return_value=list(reflected_shas)),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t07")

        assert result.ok is True
        assert result.output["total_commits"] == 3
        assert result.output["reflected_count"] == 2
        assert result.output["gap_count"] == 1
        assert abs(result.output["coverage_pct"] - 66.7) < 1.0

    @pytest.mark.asyncio
    async def test_gap_list_populated(self, db):
        db_path, conn = db
        commits = ["aaa11111", "bbb22222"]
        reflected_shas: list[str] = []

        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect._git_commits_last_7_days", return_value=commits),
            patch("sovereign_agent.tools.git_reflect._git_reflect_atoms", return_value=reflected_shas),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t08")

        assert result.ok is True
        assert set(result.output["commits_without_reflection"]) == {"aaa11111", "bbb22222"}

    @pytest.mark.asyncio
    async def test_no_git_repo_returns_ok(self, db):
        db_path, conn = db
        with (
            _patch_db(db_path),
            patch("sovereign_agent.tools.git_reflect._git_commits_last_7_days", return_value=[]),
            patch("sovereign_agent.tools.git_reflect._git_reflect_atoms", return_value=[]),
        ):
            result = await self.tool.execute(self.tool.Args(), trace_id="t09")

        assert result.ok is True
        assert result.output["total_commits"] == 0
        assert result.output["coverage_pct"] == 0.0
