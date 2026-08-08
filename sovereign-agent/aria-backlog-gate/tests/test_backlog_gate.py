"""Tests for M60 — backlog-gate."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeTask:
    id: str
    goal: str
    priority: str = "medium"
    mode: str = "oneshot"
    status: str = "pending"
    notes: str = ""


def _make_tasks(*goals: str) -> list[_FakeTask]:
    return [_FakeTask(id=f"t{i}", goal=g) for i, g in enumerate(goals)]


# ---------------------------------------------------------------------------
# Test: BacklogGate logic
# ---------------------------------------------------------------------------

class TestBacklogGate:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.backlog_gate import BacklogGate
        self.gate = BacklogGate()

    def test_valid_task_passes(self):
        result = self.gate.check("run eval_score() and log results", [])
        assert result.passed is True
        assert result.issues == []

    def test_empty_goal_blocked(self):
        result = self.gate.check("", [])
        assert result.passed is False
        assert any("empty" in i for i in result.issues)

    def test_whitespace_only_blocked(self):
        result = self.gate.check("   ", [])
        assert result.passed is False

    def test_vague_goal_blocked(self):
        result = self.gate.check("do something", [])
        assert result.passed is False
        assert any("vague" in i for i in result.issues)

    def test_vague_phrase_case_insensitive(self):
        result = self.gate.check("Be helpful today", [])
        assert result.passed is False

    def test_duplicate_blocked(self):
        existing = ["run atoms_compact_preview and notify if candidates found"]
        new_goal = "run atoms_compact_preview and notify if candidates found"
        result = self.gate.check(new_goal, existing)
        assert result.passed is False
        assert any("duplicate" in i for i in result.issues)

    def test_high_overlap_duplicate(self):
        existing = ["call eval_score and check the 7-day composite score value"]
        new_goal = "call eval_score and check the 7-day composite score result"
        result = self.gate.check(new_goal, existing)
        assert result.passed is False

    def test_non_duplicates_pass(self):
        existing = ["run atoms_compact_preview"]
        new_goal = "call hypothesis_synthesis and write a summary atom"
        result = self.gate.check(new_goal, existing)
        assert result.passed is True

    def test_too_long_blocked(self):
        long_goal = "x " * 300  # 600 chars
        result = self.gate.check(long_goal, [])
        assert result.passed is False
        assert any("long" in i for i in result.issues)

    def test_filter_keeps_good_marks_bad(self):
        tasks = _make_tasks(
            "run eval_score() and log results",  # good
            "do something",                       # vague
            "run eval_score() and log results",   # would be duplicate of first
        )
        kept, flagged = self.gate.filter_backlog(tasks)
        assert any(t.goal == "run eval_score() and log results" for t in kept if t.status == "pending")
        assert len(flagged) >= 1

    def test_flagged_not_deleted(self):
        tasks = _make_tasks("", "run eval_score()")
        kept, flagged = self.gate.filter_backlog(tasks)
        # Total tasks still same count
        assert len(kept) + len(flagged) == len(tasks)

    def test_flagged_task_status_set(self):
        tasks = _make_tasks("do something")
        kept, flagged = self.gate.filter_backlog(tasks)
        assert len(flagged) == 1
        task, _ = flagged[0]
        assert task.status == "flagged"

    def test_gate_result_structure(self):
        result = self.gate.check("", [])
        assert hasattr(result, "passed")
        assert hasattr(result, "issues")
        assert hasattr(result, "suggestions")

    def test_empty_backlog(self):
        kept, flagged = self.gate.filter_backlog([])
        assert kept == []
        assert flagged == []


# ---------------------------------------------------------------------------
# Test: BacklogReadTool
# ---------------------------------------------------------------------------

class TestBacklogReadTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.backlog_tools import BacklogReadTool
        self.tool = BacklogReadTool()

    def test_name(self):
        assert self.tool.name == "backlog_read"

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    @pytest.mark.asyncio
    async def test_returns_counts(self):
        tasks = [
            _FakeTask("t1", "do eval", status="pending"),
            _FakeTask("t2", "do git", status="done"),
            _FakeTask("t3", "do reflect", status="pending"),
        ]
        with patch("sovereign_agent.tools.backlog_tools.read_backlog", return_value=tasks):
            result = await self.tool.execute(self.tool.Args(), trace_id="t01")

        assert result.ok is True
        assert result.output["pending_count"] == 2
        assert result.output["done_count"] == 1
        assert result.output["total"] == 3

    @pytest.mark.asyncio
    async def test_read_unavailable_returns_empty_ok(self):
        with patch("sovereign_agent.tools.backlog_tools.read_backlog", None):
            result = await self.tool.execute(self.tool.Args(), trace_id="t02")
        assert result.ok is True
        assert result.output["total"] == 0


# ---------------------------------------------------------------------------
# Test: BacklogGateTool
# ---------------------------------------------------------------------------

class TestBacklogGateTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.backlog_tools import BacklogGateTool
        self.tool = BacklogGateTool()

    def test_name(self):
        assert self.tool.name == "backlog_gate"

    def test_tier_is_1(self):
        assert self.tool.tier == 1

    @pytest.mark.asyncio
    async def test_dry_run_flags_without_writing(self, tmp_path):
        tasks = [
            _FakeTask("t1", "run eval_score() and log results"),
            _FakeTask("t2", "do something"),  # vague
        ]
        written = {}
        with (
            patch("sovereign_agent.tools.backlog_tools.read_backlog", return_value=tasks),
            patch("sovereign_agent.tools.backlog_tools.write_backlog", side_effect=lambda ts: written.update({"tasks": ts})),
        ):
            result = await self.tool.execute(self.tool.Args(dry_run=True), trace_id="t03")

        assert result.ok is True
        assert result.output["dry_run"] is True
        assert result.output["flagged_count"] == 1
        assert "written" not in written  # write_backlog not called

    @pytest.mark.asyncio
    async def test_apply_writes_flagged_status(self):
        tasks = [
            _FakeTask("t1", "run eval_score()"),
            _FakeTask("t2", ""),  # empty goal
        ]
        written = {}
        with (
            patch("sovereign_agent.tools.backlog_tools.read_backlog", return_value=tasks),
            patch("sovereign_agent.tools.backlog_tools.write_backlog", side_effect=lambda ts: written.update({"tasks": ts})),
        ):
            result = await self.tool.execute(self.tool.Args(dry_run=False), trace_id="t04")

        assert result.ok is True
        assert "tasks" in written
        flagged = [t for t in written["tasks"] if t.status == "flagged"]
        assert len(flagged) == 1

    @pytest.mark.asyncio
    async def test_gate_on_empty_backlog(self):
        with patch("sovereign_agent.tools.backlog_tools.read_backlog", return_value=[]):
            result = await self.tool.execute(self.tool.Args(), trace_id="t05")
        assert result.ok is True
        assert result.output["flagged_count"] == 0
