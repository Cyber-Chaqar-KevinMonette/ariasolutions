"""Tests for goal_modulator — turning one open-ended goal into a real
subtask queue with an explicit timeframe + end goal per subtask, before
the session ever starts.

Kevin, 2026-07-21: "Also add a helper or something to turn ingestion into
smaller task. A god tier goal to task modulator." Then: "Every ingestion
should be broken down into timeframes and end goals, basically."

Root cause this closes: a goal like "stay busy for 2h43m..." used to
become ONE subtask that hit its own 600s per-subtask wall-clock ceiling in
~10 minutes, nowhere near the requested duration -- the stated duration
was just text a model read, never a real technical limit.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# ── extract_target_minutes ──────────────────────────────────────────────


def test_extracts_hours_and_minutes_combined():
    from sovereign_agent.goal_modulator import extract_target_minutes

    assert extract_target_minutes(
        "You have 2 hours and 43ish minutes to stay busy"
    ) == 163  # 120 + 43


def test_extracts_bare_hours():
    from sovereign_agent.goal_modulator import extract_target_minutes

    assert extract_target_minutes("work for 3 hours") == 180
    assert extract_target_minutes("give me 1.5 hr of research") == 90


def test_extracts_bare_minutes():
    from sovereign_agent.goal_modulator import extract_target_minutes

    assert extract_target_minutes("run for 90 minutes") == 90
    assert extract_target_minutes("just 20 min, please") == 20


def test_returns_none_when_no_duration_stated():
    from sovereign_agent.goal_modulator import extract_target_minutes

    assert extract_target_minutes("fix the typo in README.md") is None


# ── suggests_decomposition ───────────────────────────────────────────────


def test_suggests_decomposition_true_for_stated_duration():
    from sovereign_agent.goal_modulator import suggests_decomposition

    assert suggests_decomposition("stay busy for 2 hours") is True


def test_suggests_decomposition_true_for_open_ended_phrasing():
    from sovereign_agent.goal_modulator import suggests_decomposition

    assert suggests_decomposition("explore ways to improve yourself") is True


def test_suggests_decomposition_false_for_a_concrete_goal():
    from sovereign_agent.goal_modulator import suggests_decomposition

    assert suggests_decomposition("fix the typo in README.md") is False


# ── modulate_goal ─────────────────────────────────────────────────────────


def _fake_client(response_text: str):
    client = AsyncMock()
    client.chat = AsyncMock(return_value={"message": {"content": response_text}})
    return client


@pytest.mark.asyncio
async def test_modulate_goal_parses_real_next_subtask_format():
    from sovereign_agent.goal_modulator import modulate_goal

    text = (
        "NEXT_SUBTASK[tier=1]: Read SPRINT_MODE_BRIEFING.md "
        "(target: ~10 min; done when: summarized in one paragraph)\n"
        "NEXT_SUBTASK[tier=1]: List every tool available "
        "(target: ~15 min; done when: a full list is written)\n"
    )
    specs = await modulate_goal("stay busy for an hour", client=_fake_client(text))
    assert len(specs) == 2
    assert specs[0][1] == 1  # tier
    assert "SPRINT_MODE_BRIEFING.md" in specs[0][0]
    assert "target:" in specs[0][0] and "done when:" in specs[0][0]


@pytest.mark.asyncio
async def test_modulate_goal_uses_the_fast_model_by_default():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.goal_modulator import modulate_goal

    client = _fake_client("NEXT_SUBTASK[tier=1]: a step\n")
    await modulate_goal("do something", client=client)
    called_model = client.chat.call_args.kwargs.get("model")
    assert called_model == SETTINGS.fast_model


@pytest.mark.asyncio
async def test_modulate_goal_degrades_to_empty_on_unreachable_model():
    from sovereign_agent.goal_modulator import modulate_goal

    client = AsyncMock()
    client.chat = AsyncMock(side_effect=OSError("connection refused"))
    assert await modulate_goal("do something", client=client) == []


@pytest.mark.asyncio
async def test_modulate_goal_degrades_to_empty_on_blank_response():
    from sovereign_agent.goal_modulator import modulate_goal

    assert await modulate_goal("do something", client=_fake_client("")) == []


@pytest.mark.asyncio
async def test_modulate_goal_degrades_to_empty_on_malformed_tier():
    """parse_proposals() raises SessionError on an out-of-range tier --
    modulation must swallow that as a clean [] fallback, never propagate."""
    from sovereign_agent.goal_modulator import modulate_goal

    text = "NEXT_SUBTASK[tier=9]: something needing tier 9\n"
    assert await modulate_goal("do something", client=_fake_client(text)) == []


@pytest.mark.asyncio
async def test_modulate_goal_degrades_to_empty_on_prose_with_no_next_subtask_lines():
    """A model that ignores the format instructions (plain prose,
    no NEXT_SUBTASK lines at all) must degrade cleanly, not crash."""
    from sovereign_agent.goal_modulator import modulate_goal

    text = "Sure! I'll get started on that right away."
    assert await modulate_goal("do something", client=_fake_client(text)) == []


@pytest.mark.asyncio
async def test_modulate_goal_respects_an_explicit_target_minutes_override():
    from sovereign_agent.goal_modulator import modulate_goal

    client = _fake_client("NEXT_SUBTASK[tier=1]: a step\n")
    await modulate_goal("do something", target_minutes=45, client=client)
    prompt = client.chat.call_args.kwargs["messages"][0]["content"]
    assert "45 minutes" in prompt


@pytest.mark.asyncio
async def test_modulate_goal_falls_back_to_extracted_minutes_when_not_given():
    from sovereign_agent.goal_modulator import modulate_goal

    client = _fake_client("NEXT_SUBTASK[tier=1]: a step\n")
    await modulate_goal("stay busy for 2 hours", client=client)
    prompt = client.chat.call_args.kwargs["messages"][0]["content"]
    assert "120 minutes" in prompt
