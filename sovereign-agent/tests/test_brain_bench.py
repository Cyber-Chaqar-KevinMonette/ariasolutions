"""Tests for brain benchmark (honest speed) + flood-guarded free speech."""
from __future__ import annotations

import asyncio
import pytest


def _bench():
    from sovereign_agent.quantum import brain_bench
    return brain_bench


def test_benchmark_reports_latency(tmp_path):
    b = _bench()
    r = b.benchmark(tmp_path, runs=10, length=60)
    assert r["mean_ms"] > 0
    assert "p50_ms" in r and "p95_ms" in r
    assert r["local_only"] is True
    assert "honest_caveat" in r            # honesty is mandatory


def test_free_speak_flood_guard(tmp_path):
    b = _bench()
    r = b.free_speak(tmp_path, length=1200, temp=0.3, max_chars=200)
    assert r["chars"] <= 200
    assert r["flood_capped"] is True       # the hard cap holds


def test_free_speak_returns_text(tmp_path):
    b = _bench()
    r = b.free_speak(tmp_path, length=80, temp=0.2, max_chars=2000)
    assert isinstance(r["text"], str) and len(r["text"]) > 0
    assert 0.0 <= r["vocab_coherence"] <= 1.0


# ── tools ─────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_benchmark_tool_t0():
    from sovereign_agent.tools.brain_bench_tools import BrainBenchmarkTool
    t = BrainBenchmarkTool()
    assert t.tier == 0
    res = _run(t.execute(t.Args(runs=8, length=50), trace_id="t"))
    assert res.ok and res.output["mean_ms"] > 0


def test_speak_tool_t1_flood_capped():
    from sovereign_agent.tools.brain_bench_tools import BrainSpeakTool
    t = BrainSpeakTool()
    assert t.tier == 1
    res = _run(t.execute(t.Args(length=1200, temp=0.3, max_chars=150), trace_id="t"))
    assert res.ok and res.output["chars"] <= 150
