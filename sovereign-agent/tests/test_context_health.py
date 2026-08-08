"""Tests for context_health — the 0-100% context-window and run-budget
gauges. Pure function, no I/O."""
from __future__ import annotations

from sovereign_agent.context_health import (
    BUDGET_CRITICAL_PCT,
    BUDGET_WARN_PCT,
    WINDOW_CRITICAL_PCT,
    WINDOW_WARN_PCT,
    assess,
)

NUM_CTX = 16384
MAX_TOKENS = 200_000


def test_zero_usage_is_fully_healthy():
    h = assess(0, 0, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.window_fill_pct == 0.0
    assert h.budget_fill_pct == 0.0
    assert h.window_level == "ok"
    assert h.budget_level == "ok"


def test_window_pct_matches_prompt_tokens_over_num_ctx():
    h = assess(8192, 0, num_ctx=16384, max_tokens=MAX_TOKENS)
    assert h.window_fill_pct == 50.0


def test_budget_pct_matches_running_total_over_max_tokens():
    h = assess(0, 100_000, num_ctx=NUM_CTX, max_tokens=200_000)
    assert h.budget_fill_pct == 50.0


def test_window_level_ok_below_warn_threshold():
    pct_tokens = int(NUM_CTX * (WINDOW_WARN_PCT - 1) / 100)
    h = assess(pct_tokens, 0, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.window_level == "ok"


def test_window_level_warn_at_threshold():
    tokens = int(NUM_CTX * WINDOW_WARN_PCT / 100)
    h = assess(tokens, 0, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.window_level == "warn"


def test_window_level_critical_at_threshold():
    tokens = int(NUM_CTX * WINDOW_CRITICAL_PCT / 100)
    h = assess(tokens, 0, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.window_level == "critical"


def test_budget_level_warn_at_threshold():
    total = int(MAX_TOKENS * BUDGET_WARN_PCT / 100)
    h = assess(0, total, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.budget_level == "warn"


def test_budget_level_critical_at_threshold():
    total = int(MAX_TOKENS * BUDGET_CRITICAL_PCT / 100)
    h = assess(0, total, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.budget_level == "critical"


def test_pct_is_capped_at_100():
    h = assess(999_999, 999_999_999, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.window_fill_pct == 100.0
    assert h.budget_fill_pct == 100.0


def test_negative_inputs_never_go_negative():
    h = assess(-5, -10, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert h.window_fill_pct == 0.0
    assert h.budget_fill_pct == 0.0


def test_zero_ceiling_never_divides_by_zero():
    h = assess(100, 100, num_ctx=0, max_tokens=0)
    assert h.window_fill_pct == 0.0
    assert h.budget_fill_pct == 0.0


def test_recommendation_follows_the_more_urgent_signal():
    # window critical, budget ok -> window message wins
    h = assess(int(NUM_CTX * 0.9), 0, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert "compact now" in h.recommendation

    # budget critical, window ok -> budget message wins
    h = assess(0, int(MAX_TOKENS * 0.95), num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    assert "clear-session" in h.recommendation


def test_as_dict_shape():
    h = assess(100, 200, num_ctx=NUM_CTX, max_tokens=MAX_TOKENS)
    d = h.as_dict()
    assert set(d.keys()) == {
        "window_fill_pct", "window_level", "budget_fill_pct", "budget_level", "recommendation"}
