"""Tests for aria-timeout-gate: the live, standing gate — real
events.jsonl, no ledger writes (that's the sentinel's job in T3)."""
from __future__ import annotations

import pytest


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir.parent))
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()
    original = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield data_dir
    finally:
        object.__setattr__(SETTINGS, "paths", original)


def test_no_history_passes_honestly(isolated_paths):
    from sovereign_agent.timeouts.gate import gate

    verdict = gate(data_dir=isolated_paths)
    assert verdict.verdict == "PASS"


def test_a_single_unexplained_timeout_warns(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts.gate import gate

    emit_event("some-new-subsystem-timeout-d", plane="control", trace_id="x",
               payload={"tool": "brand_new_thing", "timeout_seconds": 5.0})

    verdict = gate(data_dir=isolated_paths)
    assert verdict.verdict == "WARN"
    assert verdict.unexplained_count == 1


def test_three_recurring_unexplained_timeouts_for_the_same_tool_blocks(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts.gate import gate

    for _ in range(3):
        emit_event("flaky-thing-timeout-d", plane="control", trace_id="x",
                   payload={"tool": "flaky_thing", "timeout_seconds": 5.0})

    verdict = gate(data_dir=isolated_paths)
    assert verdict.verdict == "BLOCK"
    assert "flaky_thing" in verdict.recurring_tools


def test_a_justified_catalogued_timeout_passes(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts.gate import gate

    emit_event("vram-lock-timeout-d", plane="control", trace_id="vram",
               payload={"tool": "aria_lm.grow_mind", "timeout_seconds": 60.0})

    verdict = gate(data_dir=isolated_paths)
    assert verdict.verdict == "PASS"


def test_gate_does_not_write_to_the_ledger(isolated_paths):
    from sovereign_agent.timeouts.gate import gate
    from sovereign_agent.timeouts.ledger import latest_timeout_scan

    gate(data_dir=isolated_paths)
    gate(data_dir=isolated_paths)
    assert latest_timeout_scan(isolated_paths) is None


def test_kill_switch_degrades_to_pass(isolated_paths, monkeypatch):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts.gate import gate

    for _ in range(3):
        emit_event("flaky-thing-timeout-d", plane="control", trace_id="x",
                   payload={"tool": "flaky_thing", "timeout_seconds": 5.0})
    monkeypatch.setenv("SOV_NO_TIMEOUT_GATE", "1")

    verdict = gate(data_dir=isolated_paths)
    assert verdict.verdict == "PASS"
    assert "kill-switched" in verdict.notes[0]
