"""Tests for curate_training_data_tool — Aria's own hands on the fine-tune
data pipeline (Tier 1).

Kevin, 2026-07-21: "Prepare Aria and me for this work."
"""
from __future__ import annotations

import pytest


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "curate_training_data" in _TIER_REGISTRY
    assert _TIER_REGISTRY["curate_training_data"].tier == 1


@pytest.mark.asyncio
async def test_execute_runs_the_real_pipeline_and_writes_the_dataset(tmp_path):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools.curate_training_data_tool import CurateTrainingDataTool

    tool = CurateTrainingDataTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["output_count"] == 0  # no real history in this isolated tmp dir
    expected_path = SETTINGS.paths.data_dir / "training" / "dataset.jsonl"
    assert expected_path.exists()


@pytest.mark.asyncio
async def test_execute_reports_a_real_yield_from_real_data():
    from sovereign_agent.agent_session import Subtask, SessionStore, SessionState
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools.curate_training_data_tool import CurateTrainingDataTool

    store = SessionStore(SETTINGS.paths.data_dir / "sessions")
    store.save(SessionState(
        session_id="sess_tool_test", goal="g", mode="busy",
        subtasks=[Subtask(id="st_a", description="a genuinely real completed subtask",
                          status="done", result_summary="a genuinely real result summary")],
    ))

    tool = CurateTrainingDataTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["output_count"] == 1
    assert result.metadata["output_count"] == 1


@pytest.mark.asyncio
async def test_execute_never_raises_on_a_broken_source(monkeypatch):
    from sovereign_agent.tools.curate_training_data_tool import CurateTrainingDataTool
    import sovereign_agent.training_data as td

    def _boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(td, "build_training_dataset", _boom)
    tool = CurateTrainingDataTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert not result.ok
    assert "curation failed" in result.error
