"""test_emotion_crown.py — Tests for M44 (8-Dimensional Emotion Engine)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── derive_emotions unit tests ────────────────────────────────────────────────


def test_derive_emotions_zero_events():
    from sovereign_agent.emotion import derive_emotions
    state = derive_emotions(events=[], vram_info=None, session_stats=None)
    assert 0.0 <= state.focus <= 1.0
    assert 0.0 <= state.curiosity <= 1.0
    assert 0.0 <= state.concern <= 1.0
    assert 0.0 <= state.satisfaction <= 1.0
    assert 0.0 <= state.fatigue <= 1.0
    assert 0.0 <= state.care <= 1.0
    assert 0.0 <= state.enthusiasm <= 1.0
    assert 0.0 <= state.uncertainty <= 1.0


def test_derive_emotions_high_error_rate_raises_concern():
    from sovereign_agent.emotion import derive_emotions
    events = [
        {"flag": "tool-start-d", "payload": {"tool": "run_command"}},
        {"flag": "tool-x", "payload": {"tool": "run_command", "error": "fail"}},
        {"flag": "tool-start-d", "payload": {"tool": "run_command"}},
        {"flag": "tool-x", "payload": {"tool": "run_command", "error": "fail"}},
        {"flag": "tool-start-d", "payload": {"tool": "run_command"}},
        {"flag": "tool-x", "payload": {"tool": "run_command", "error": "fail"}},
    ]
    state = derive_emotions(events=events)
    assert state.concern > 0.3, f"Expected concern > 0.3, got {state.concern}"


def test_derive_emotions_commits_raise_satisfaction():
    from sovereign_agent.emotion import derive_emotions
    events = [
        {"flag": "commit-d", "payload": {"message": "feat: add M43"}},
        {"flag": "commit-d", "payload": {"message": "feat: add M44"}},
        {"flag": "commit-d", "payload": {"message": "feat: tests pass"}},
    ]
    state = derive_emotions(events=events)
    assert state.satisfaction > 0.5, f"Expected satisfaction > 0.5, got {state.satisfaction}"


def test_derive_emotions_low_vram_raises_concern():
    from sovereign_agent.emotion import derive_emotions
    state = derive_emotions(events=[], vram_info={"free_mb": 300})
    assert state.concern > 0.4, f"Expected concern > 0.4 with low VRAM, got {state.concern}"


def test_derive_emotions_all_values_0_to_1():
    from sovereign_agent.emotion import derive_emotions
    events = [
        {"flag": "commit-d", "payload": {}},
        {"flag": "tool-start-d", "payload": {}},
        {"flag": "tool-x", "payload": {}},
    ]
    state = derive_emotions(events=events, vram_info={"free_mb": 2000})
    for dim, val in state.scores().items():
        assert 0.0 <= val <= 1.0, f"{dim} = {val} out of range"


def test_primary_emotion_is_valid_dimension():
    from sovereign_agent.emotion import derive_emotions
    state = derive_emotions(events=[], vram_info={"free_mb": 4000})
    valid = {"focus", "curiosity", "satisfaction", "care", "enthusiasm"}
    assert state.primary_emotion in valid, f"Invalid primary_emotion: {state.primary_emotion}"


def test_narrative_is_non_empty():
    from sovereign_agent.emotion import derive_emotions
    state = derive_emotions(events=[])
    assert isinstance(state.narrative, str)
    assert len(state.narrative) > 10


def test_emotion_to_mood():
    from sovereign_agent.emotion import EmotionState, emotion_to_mood
    state = EmotionState()
    state.concern = 0.8
    assert emotion_to_mood(state) == "concerned"

    state2 = EmotionState()
    state2.satisfaction = 0.8
    state2.concern = 0.2
    assert emotion_to_mood(state2) == "satisfied"


def test_emotion_state_as_dict():
    from sovereign_agent.emotion import EmotionState
    state = EmotionState()
    d = state.as_dict()
    assert "focus" in d
    assert "concern" in d
    assert "narrative" in d
    assert "primary_emotion" in d


# ── Tool registration tests ───────────────────────────────────────────────────


def test_emotion_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "get_emotions" in _TIER_REGISTRY
    assert "emotion_note" in _TIER_REGISTRY
    assert "emotion_history" in _TIER_REGISTRY
    assert "emotion_report" in _TIER_REGISTRY
    assert _TIER_REGISTRY["get_emotions"].tier == 0
    assert _TIER_REGISTRY["emotion_note"].tier == 1
    assert _TIER_REGISTRY["emotion_history"].tier == 0
    assert _TIER_REGISTRY["emotion_report"].tier == 0


def test_emotion_tools_have_failure_modes():
    from sovereign_agent.tools.emotion_tools import (
        GetEmotionsTool, EmotionNoteTool, EmotionHistoryTool, EmotionReportTool,
    )
    for cls in (GetEmotionsTool, EmotionNoteTool, EmotionHistoryTool, EmotionReportTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── get_emotions tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_emotions_returns_all_dimensions():
    from sovereign_agent.tools.emotion_tools import GetEmotionsTool
    from sovereign_agent.emotion import EmotionState
    tool = GetEmotionsTool()
    mock_state = EmotionState(
        focus=0.7, curiosity=0.5, concern=0.2, satisfaction=0.6,
        fatigue=0.1, care=0.8, enthusiasm=0.6, uncertainty=0.3,
        primary_emotion="care", narrative="Session going well.",
    )
    with patch("sovereign_agent.tools.emotion_tools.derive_emotions", return_value=mock_state):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "dimensions" in result.output
    assert "focus" in result.output["dimensions"]
    assert "primary_emotion" in result.output
    assert result.output["primary_emotion"] == "care"
    assert result.output["narrative"] == "Session going well."


@pytest.mark.asyncio
async def test_get_emotions_flags_high_concern():
    from sovereign_agent.tools.emotion_tools import GetEmotionsTool
    from sovereign_agent.emotion import EmotionState
    tool = GetEmotionsTool()
    mock_state = EmotionState(concern=0.8, primary_emotion="concern",
                               narrative="Concern elevated.")
    with patch("sovereign_agent.tools.emotion_tools.derive_emotions", return_value=mock_state):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["attention"] is not None
    assert "CONCERN" in result.output["attention"]


# ── emotion_note tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emotion_note_invalid_dimension():
    from sovereign_agent.tools.emotion_tools import EmotionNoteTool
    tool = EmotionNoteTool()
    result = await tool.execute(
        tool.Args(dimension="happiness", context="test", intensity=0.5),
        trace_id="t1",
    )
    assert not result.ok
    assert "Invalid dimension" in result.error


@pytest.mark.asyncio
async def test_emotion_note_writes_atom():
    from sovereign_agent.tools.emotion_tools import EmotionNoteTool
    tool = EmotionNoteTool()
    mock_conn = MagicMock()
    with (
        patch("sovereign_agent.tools.emotion_tools.open_atoms_db", return_value=mock_conn),
        patch("sovereign_agent.tools.emotion_tools.write_atom", return_value="atom-123"),
    ):
        result = await tool.execute(
            tool.Args(dimension="concern", context="3 test failures in a row", intensity=0.7),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["dimension"] == "concern"
    assert result.output["intensity"] == 0.7


# ── emotion_history tool tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emotion_history_returns_entries():
    from sovereign_agent.tools.emotion_tools import EmotionHistoryTool
    import json
    tool = EmotionHistoryTool()
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_rows = [
        ("atom-1", "concern (70%): test failed", json.dumps({"dimension": "concern", "intensity": 0.7, "context": "test failed"}), "2026-06-20T01:00:00"),
        ("atom-2", "satisfaction (80%): commit done", json.dumps({"dimension": "satisfaction", "intensity": 0.8, "context": "commit done"}), "2026-06-20T00:30:00"),
    ]
    mock_conn.execute.return_value.fetchall.return_value = mock_rows
    with patch("sovereign_agent.tools.emotion_tools.open_atoms_db", return_value=mock_conn):
        result = await tool.execute(tool.Args(limit=10), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 2


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_emotion_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "emotion-crown-d" in src, "emotion-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
