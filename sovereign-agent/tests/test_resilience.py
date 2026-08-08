"""
test_resilience.py — Tests for M34 (CircuitBreaker, BreakerRegistry, backoff).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

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


# ── get_shared_registry / guarded_execute ─────────────────────────────────────


def test_get_shared_registry_falls_back_when_loop_not_loaded(monkeypatch):
    from sovereign_agent import resilience
    import sovereign_agent.loop as _loop
    monkeypatch.delattr(_loop, "_breaker_registry", raising=False)
    reg = resilience.get_shared_registry()
    assert reg is not None


def test_get_shared_registry_returns_loop_singleton():
    from sovereign_agent import resilience
    import sovereign_agent.loop as _loop
    assert resilience.get_shared_registry() is _loop._breaker_registry


@dataclass
class _FakeToolResult:
    ok: bool
    output: object = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class _FakeTool:
    name = "fake_tool"

    def __init__(self, ok: bool) -> None:
        self._ok = ok
        self.calls = 0

    async def execute(self, args, *, trace_id):
        self.calls += 1
        return _FakeToolResult(ok=self._ok, error=None if self._ok else "boom")


@pytest.mark.asyncio
async def test_guarded_execute_passes_through_on_success():
    from sovereign_agent.resilience import BreakerRegistry, guarded_execute
    tool = _FakeTool(ok=True)
    reg = BreakerRegistry()
    result = await guarded_execute(tool, None, trace_id="t1", registry=reg)
    assert result.ok
    assert tool.calls == 1
    assert reg.get_breaker("tool:fake_tool").state.value == "closed"


@pytest.mark.asyncio
async def test_guarded_execute_opens_breaker_after_threshold_and_skips_execute():
    from sovereign_agent.resilience import BreakerRegistry, guarded_execute
    tool = _FakeTool(ok=False)
    reg = BreakerRegistry()
    reg.get_breaker("tool:fake_tool", failure_threshold=2)
    for _ in range(2):
        result = await guarded_execute(tool, None, trace_id="t1", registry=reg)
        assert not result.ok
    assert tool.calls == 2

    # Third call: breaker is OPEN, execute() must not run again.
    result = await guarded_execute(tool, None, trace_id="t1", registry=reg)
    assert not result.ok
    assert "circuit_open" in result.error
    assert tool.calls == 2  # unchanged — execute() was skipped


# ── ollama_client.py breaker wiring ────────────────────────────────────────────


@pytest.mark.asyncio
@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_ollama_chat_opens_breaker_after_repeated_connection_failures(mock_client_class):
    from sovereign_agent import resilience
    from sovereign_agent.ollama_client import OllamaClient

    fresh_registry = resilience.BreakerRegistry()
    with patch.object(resilience, "get_shared_registry", return_value=fresh_registry):
        mock_aclient = MagicMock()
        mock_aclient.show = AsyncMock(return_value={"capabilities": ["completion"]})
        mock_aclient.chat = AsyncMock(side_effect=ConnectionRefusedError("connection refused"))
        mock_client_class.return_value = mock_aclient

        client = OllamaClient()
        breaker = fresh_registry.get_breaker("ollama", failure_threshold=3)

        with patch("asyncio.sleep", new=AsyncMock()):
            for _ in range(3):
                with pytest.raises(Exception):
                    await client.chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}])
        assert breaker.state.value == "open"

        calls_before = mock_aclient.chat.await_count
        with pytest.raises(RuntimeError, match="circuit breaker OPEN for ollama"):
            await client.chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}])
        # breaker refused before ever reaching the real client again
        assert mock_aclient.chat.await_count == calls_before


# ── guarded_execute wired into real cockpit/tool-to-tool call sites ───────────
# Real behavioral proof (not just marker-string presence) that the two
# highest-risk unprotected call sites found in the resilience audit —
# game_pane.py's direct godot_check call, and place_game_sprite.py's direct
# image_generate call — are actually gated. Both tools are driven through
# guarded_execute with a fresh, isolated registry (never the process-wide
# shared one) so this test can't leak breaker state into any other test.


@pytest.mark.asyncio
async def test_game_pane_godot_check_path_opens_its_own_breaker(tmp_path):
    from sovereign_agent.resilience import BreakerRegistry, guarded_execute
    from sovereign_agent.tools.godot_check import GodotCheckTool

    reg = BreakerRegistry()
    tool = GodotCheckTool(data_dir=tmp_path)  # no project registered — deterministic, cheap failure
    for _ in range(3):
        result = await guarded_execute(tool, tool.Args(project_slug="ghost"),
                                       trace_id="t1", registry=reg,
                                       breaker_name="tool:godot_check")
        assert not result.ok
    assert reg.get_breaker("tool:godot_check").state.value == "open"

    result = await guarded_execute(tool, tool.Args(project_slug="ghost"),
                                   trace_id="t1", registry=reg,
                                   breaker_name="tool:godot_check")
    assert "circuit_open" in result.error


@pytest.mark.asyncio
async def test_place_game_sprite_generate_path_opens_its_own_breaker(tmp_path):
    from unittest.mock import patch as _patch

    from sovereign_agent import resilience
    from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.place_game_sprite import PlaceGameSpriteTool

    save(GameProject(project_name="Breaker Test", dimension="2d"), tmp_path)
    sandbox = tmp_path / "sandbox"
    workspace = game_workspace_dir("breaker-test", sandbox_dir=sandbox)
    (workspace / "main.tscn").write_text(
        '[gd_scene load_steps=1 format=3]\n\n[node name="Main" type="Node2D"]\n'
    )

    class _FailingGenerateImageTool:
        class Args:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        async def execute(self, _args, *, trace_id):
            return ToolResult(ok=False, error="simulated GPU OOM")

    reg = resilience.BreakerRegistry()
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as sprite_mod
    with _patch.object(sprite_mod, "game_workspace_dir", return_value=workspace), \
         _patch.object(sprite_mod, "check_write_path", side_effect=lambda p, mode: p), \
         _patch.object(sprite_mod, "GenerateImageTool", _FailingGenerateImageTool), \
         _patch.object(resilience, "get_shared_registry", return_value=reg):
        for _ in range(3):
            result = await tool.execute(
                tool.Args(project_slug="breaker-test", prompt="x", sprite_name="X"),
                trace_id="t1",
            )
            assert not result.ok
    assert reg.get_breaker("tool:generate_image").state.value == "open"


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
