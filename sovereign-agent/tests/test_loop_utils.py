"""Tests for loop.py utility functions — coverage of testable helpers.

The main agent_loop() body requires live Ollama and is intentionally not
unit-tested here. These tests cover the pure utility functions that can
run offline.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sovereign_agent.modes import BudgetExceeded, Mode, RunBudget


# ── _check_budget ─────────────────────────────────────────────────────────────


def test_check_budget_passes_when_under_all_limits():
    from sovereign_agent.loop import _check_budget
    budget = RunBudget(max_iterations=10, max_tokens=1000, max_wall_seconds=3600)
    _check_budget(budget, iter_count=5, tokens_used=500, started_at=time.monotonic())


def test_check_budget_raises_on_iteration_limit():
    from sovereign_agent.loop import _check_budget
    budget = RunBudget(max_iterations=5)
    with pytest.raises(BudgetExceeded) as exc_info:
        _check_budget(budget, iter_count=5, tokens_used=0, started_at=time.monotonic())
    assert exc_info.value.kind == "iterations"
    assert exc_info.value.used == 5
    assert exc_info.value.limit == 5


def test_check_budget_raises_on_token_limit():
    from sovereign_agent.loop import _check_budget
    budget = RunBudget(max_tokens=100)
    with pytest.raises(BudgetExceeded) as exc_info:
        _check_budget(budget, iter_count=0, tokens_used=100, started_at=time.monotonic())
    assert exc_info.value.kind == "tokens"


def test_check_budget_raises_on_wall_time():
    from sovereign_agent.loop import _check_budget
    budget = RunBudget(max_wall_seconds=0)
    with pytest.raises(BudgetExceeded) as exc_info:
        _check_budget(budget, iter_count=0, tokens_used=0, started_at=time.monotonic() - 1)
    assert exc_info.value.kind == "wall_seconds"


def test_budget_exceeded_message_is_readable():
    exc = BudgetExceeded("iterations", used=25, limit=25)
    assert "iterations" in str(exc)
    assert "25" in str(exc)


# ── _read_mode_override ───────────────────────────────────────────────────────


def test_read_mode_override_returns_none_when_no_file():
    from sovereign_agent.loop import _read_mode_override
    result = _read_mode_override()
    assert result is None


def test_read_mode_override_returns_data_when_valid(tmp_path):
    from sovereign_agent.loop import _read_mode_override
    override_data = {"mode": "busy", "expires_at": time.time() + 3600}
    override_file = tmp_path / "mode_override.json"
    override_file.write_text(json.dumps(override_data))

    with patch("sovereign_agent.loop.SETTINGS") as mock_settings:
        mock_settings.data_dir = tmp_path
        result = _read_mode_override()

    assert result is not None
    assert result["mode"] == "busy"


def test_read_mode_override_returns_none_when_expired(tmp_path):
    from sovereign_agent.loop import _read_mode_override
    override_data = {"mode": "busy", "expires_at": time.time() - 1}
    override_file = tmp_path / "mode_override.json"
    override_file.write_text(json.dumps(override_data))

    with patch("sovereign_agent.loop.SETTINGS") as mock_settings:
        mock_settings.data_dir = tmp_path
        result = _read_mode_override()

    assert result is None


def test_read_mode_override_returns_none_on_corrupt_json(tmp_path):
    from sovereign_agent.loop import _read_mode_override
    override_file = tmp_path / "mode_override.json"
    override_file.write_text("not valid json {{{")

    with patch("sovereign_agent.loop.SETTINGS") as mock_settings:
        mock_settings.data_dir = tmp_path
        result = _read_mode_override()

    assert result is None


# ── _system_prompt ────────────────────────────────────────────────────────────
# Real regression test for a real, live bug: SYSTEM_PROMPT_TEMPLATE.format(...)
# used to raise KeyError('title, action_kind, action_input') because the
# template's workflow_create example used literal {curly} braces that
# str.format() tried to parse as a field name. This sat undetected for 2+
# weeks (introduced 2026-06-19) because this test file deliberately tested
# only that _system_prompt was *callable*, never actually called it — the
# exact "test exists but doesn't exercise real behavior" gap this session
# found and fixed multiple times elsewhere. Root cause fixed by escaping
# the literal braces to {{title, action_kind, action_input}} in loop.py;
# this test now actually calls _system_prompt() for every Mode.


def test_system_prompt_actually_renders_for_every_mode():
    from sovereign_agent.loop import _system_prompt
    from sovereign_agent.modes import Mode

    for mode in Mode:
        prompt = _system_prompt(mode)
        assert mode.value.upper() in prompt
        assert len(prompt) > 100


def test_system_prompt_template_is_nonempty():
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert len(SYSTEM_PROMPT_TEMPLATE) > 100


# ── LoopResult ───────────────────────────────────────────────────────────────


def test_loop_result_fields():
    from sovereign_agent.loop import LoopResult
    result = LoopResult(
        ok=True,
        reason="complete",
        iterations=3,
        tokens_used=500,
        lesson_id="abc123",
    )
    assert result.ok is True
    assert result.reason == "complete"
    assert result.iterations == 3
    assert result.tokens_used == 500
    assert result.lesson_id == "abc123"


def test_loop_result_failed_state():
    from sovereign_agent.loop import LoopResult
    result = LoopResult(ok=False, reason="budget", iterations=25, tokens_used=200_000)
    assert result.ok is False
    assert result.lesson_id is None


# ── RunBudget defaults ────────────────────────────────────────────────────────


def test_run_budget_defaults_are_safe():
    budget = RunBudget()
    assert budget.max_iterations == 25
    assert budget.max_wall_seconds == 1800
    assert budget.max_tokens == 200_000
    assert budget.consecutive_fail_limit == 3


def test_run_budget_is_frozen():
    budget = RunBudget()
    with pytest.raises((AttributeError, TypeError)):
        budget.max_iterations = 999  # type: ignore[misc]
