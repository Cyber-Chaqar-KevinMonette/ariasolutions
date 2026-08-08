"""
test_resilience.py — Tests for M34 (CircuitBreaker, BreakerRegistry, backoff).
"""
from __future__ import annotations

import pytest


# ── CircuitBreaker unit tests ─────────────────────────────────────────────────


def test_circuit_starts_closed():
    from sovereign_agent.resilience import CircuitBreaker, CircuitState
    b = CircuitBreaker(name="test")
    assert b.state == CircuitState.CLOSED
    assert b.call_allowed()


def test_circuit_opens_after_threshold():
    from sovereign_agent.resilience import CircuitBreaker, CircuitState
    b = CircuitBreaker(name="test", failure_threshold=3)
    b.record_failure()
    b.record_failure()
    assert b.state == CircuitState.CLOSED  # not yet
    b.record_failure()
    assert b.state == CircuitState.OPEN


def test_open_circuit_blocks_calls():
    from sovereign_agent.resilience import CircuitBreaker, CircuitState
    b = CircuitBreaker(name="test", failure_threshold=1)
    b.record_failure()
    assert b.state == CircuitState.OPEN
    assert not b.call_allowed()


def test_half_open_after_recovery_window():
    from sovereign_agent.resilience import CircuitBreaker, CircuitState
    import time
    b = CircuitBreaker(name="test", failure_threshold=1, recovery_window=0.01)
    b.record_failure()
    assert b.state == CircuitState.OPEN
    time.sleep(0.02)
    assert b.call_allowed()
    assert b.state == CircuitState.HALF_OPEN


def test_recovery_after_successful_probe():
    from sovereign_agent.resilience import CircuitBreaker, CircuitState
    import time
    b = CircuitBreaker(name="test", failure_threshold=1, recovery_window=0.01)
    b.record_failure()
    time.sleep(0.02)
    b.call_allowed()  # enters HALF_OPEN
    b.record_success()
    assert b.state == CircuitState.CLOSED
    assert b.call_allowed()


def test_failure_resets_count_on_success():
    from sovereign_agent.resilience import CircuitBreaker
    b = CircuitBreaker(name="test", failure_threshold=5)
    b.record_failure()
    b.record_failure()
    b.record_success()
    assert b.failure_count == 0


def test_status_returns_dict():
    from sovereign_agent.resilience import CircuitBreaker
    b = CircuitBreaker(name="my_tool")
    s = b.status()
    assert s["name"] == "my_tool"
    assert s["state"] == "closed"
    assert "failure_count" in s


# ── BreakerRegistry tests ─────────────────────────────────────────────────────


def test_registry_creates_breaker_on_demand():
    from sovereign_agent.resilience import BreakerRegistry
    r = BreakerRegistry()
    b = r.get_breaker("tool:echo")
    assert b.name == "tool:echo"


def test_registry_returns_same_breaker():
    from sovereign_agent.resilience import BreakerRegistry
    r = BreakerRegistry()
    b1 = r.get_breaker("tool:echo")
    b2 = r.get_breaker("tool:echo")
    assert b1 is b2


def test_registry_all_statuses():
    from sovereign_agent.resilience import BreakerRegistry
    r = BreakerRegistry()
    r.get_breaker("a")
    r.get_breaker("b")
    statuses = r.all_statuses()
    assert len(statuses) == 2
    names = {s["name"] for s in statuses}
    assert names == {"a", "b"}


# ── exponential_backoff tests ─────────────────────────────────────────────────


def test_backoff_grows_with_attempt():
    from sovereign_agent.resilience import exponential_backoff
    # Without jitter for determinism
    waits = [exponential_backoff(i, base=1.0, cap=60.0, jitter=False) for i in range(4)]
    assert waits[0] < waits[1] < waits[2] < waits[3]


def test_backoff_is_capped():
    from sovereign_agent.resilience import exponential_backoff
    wait = exponential_backoff(100, base=1.0, cap=10.0, jitter=False)
    assert wait == 10.0


def test_backoff_with_jitter_is_bounded():
    from sovereign_agent.resilience import exponential_backoff
    for _ in range(50):
        wait = exponential_backoff(5, base=1.0, cap=30.0, jitter=True)
        assert 0.0 <= wait <= 30.0


def test_backoff_zero_attempt():
    from sovereign_agent.resilience import exponential_backoff
    wait = exponential_backoff(0, base=1.0, cap=60.0, jitter=False)
    assert wait == 1.0  # base * 2^0 = base


# ── Tool registration tests ───────────────────────────────────────────────────


def test_resilience_status_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "resilience_status" in _TIER_REGISTRY
    assert _TIER_REGISTRY["resilience_status"].tier == 0


def test_resilience_status_tool_has_failure_modes():
    from sovereign_agent.tools.resilience_tools import ResilienceStatusTool
    assert ResilienceStatusTool.failure_modes


@pytest.mark.asyncio
async def test_resilience_status_returns_dict():
    from sovereign_agent.tools.resilience_tools import ResilienceStatusTool
    tool = ResilienceStatusTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "breakers" in result.output
    assert "total" in result.output


# ── loop.py marker tests ──────────────────────────────────────────────────────


def test_loop_has_resilience_markers():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "resilience-import-d" in src, "resilience-import-d missing"
            assert "resilience-tool-gate-d" in src, "resilience-tool-gate-d missing"
            assert "resilience-doctrine-d" in src, "resilience-doctrine-d missing"
            return
        p = p.parent
    pytest.skip("loop.py not found")
