"""Tests for bounded live mode — must be bounded, stoppable, and never flood."""
from __future__ import annotations

import asyncio
import pytest


def _live():
    from sovereign_agent.quantum import brain_live
    return brain_live


def test_ring_buffer_never_exceeds_cap(tmp_path):
    bl = _live()
    lb = bl.LiveBrain(tmp_path, buffer_size=5, tick_sleep=0.0, length=30)
    lb.run_ticks(20)                       # run more than the cap
    assert len(lb.thoughts()) == 5         # ring buffer holds only the last 5
    assert lb.status()["ticks"] == 20


def test_tick_sleep_floor_enforced(tmp_path):
    bl = _live()
    lb = bl.LiveBrain(tmp_path, tick_sleep=0.0)   # request 0
    assert lb._tick_sleep >= bl.MIN_TICK_SLEEP     # floor cannot be bypassed


def test_buffer_cap_hard_limit(tmp_path):
    bl = _live()
    lb = bl.LiveBrain(tmp_path, buffer_size=9999)  # request huge
    assert lb.thoughts() == []
    assert lb._buffer.maxlen <= bl.MAX_BUFFER       # hard cap holds


def test_threaded_start_stop_clean(tmp_path):
    bl = _live()
    lb = bl.LiveBrain(tmp_path, tick_sleep=0.05, length=20)
    assert lb.start(max_ticks=3) is True
    import time
    time.sleep(0.4)
    lb.stop(timeout=2.0)
    assert lb.status()["running"] is False
    assert lb.status()["ticks"] >= 1


def test_tick_produces_thought(tmp_path):
    bl = _live()
    lb = bl.LiveBrain(tmp_path, length=40)
    t = lb.tick()
    assert isinstance(t, str) and len(t) > 0


# ── tool ──────────────────────────────────────────────────────────────────────

def test_brain_live_tool_bounded():
    from sovereign_agent.tools.brain_live_tool import BrainLiveTool
    t = BrainLiveTool()
    assert t.tier == 1
    res = asyncio.run(t.execute(t.Args(ticks=100, length=30), trace_id="t"))   # request 100
    assert res.ok
    assert res.output["ticks_run"] <= 30                                       # hard cap to 30
    assert len(res.output["thoughts"]) <= 30
