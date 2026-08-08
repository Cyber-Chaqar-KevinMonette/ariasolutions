"""Tests for tools/context_status.py — Aria's own context-health
introspection. Mirrors tests/test_resilience.py's ResilienceStatusTool
tests."""
from __future__ import annotations

import json

import pytest


def test_context_status_tool_registered_at_tier_0():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "context_status" in _TIER_REGISTRY
    assert _TIER_REGISTRY["context_status"].tier == 0


def test_context_status_tool_has_failure_modes():
    from sovereign_agent.tools.context_status import ContextStatusTool
    assert ContextStatusTool.failure_modes


@pytest.mark.asyncio
async def test_no_events_yet_returns_honest_zero_state(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools.context_status import ContextStatusTool

    tool = ContextStatusTool(events_path=tmp_path / "events.jsonl")
    result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.ok
    assert result.output["prompt_tokens"] == 0
    assert result.output["running_total"] == 0
    assert result.output["window_level"] == "ok"
    assert "no token-usage-d events" in result.output["note"]


@pytest.mark.asyncio
async def test_reads_the_latest_token_usage_event(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools.context_status import ContextStatusTool

    events_path = tmp_path / "events.jsonl"
    records = [
        {"flag": "token-usage-d", "payload": {"prompt_tokens": 1000, "running_total": 5000}},
        {"flag": "other-event-d", "payload": {}},
        {"flag": "token-usage-d", "payload": {"prompt_tokens": 9000, "running_total": 20000}},
    ]
    events_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    tool = ContextStatusTool(events_path=events_path)
    result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.ok
    # the LAST token-usage-d event wins, not the first
    assert result.output["prompt_tokens"] == 9000
    assert result.output["running_total"] == 20000
    assert "note" not in result.output


@pytest.mark.asyncio
async def test_high_prompt_tokens_yields_critical_window_level(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools.context_status import ContextStatusTool

    events_path = tmp_path / "events.jsonl"
    rec = {"flag": "token-usage-d",
          "payload": {"prompt_tokens": int(SETTINGS.num_ctx * 0.9), "running_total": 0}}
    events_path.write_text(json.dumps(rec) + "\n")
    tool = ContextStatusTool(events_path=events_path)
    result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.output["window_level"] == "critical"
    assert "compact now" in result.output["recommendation"]
