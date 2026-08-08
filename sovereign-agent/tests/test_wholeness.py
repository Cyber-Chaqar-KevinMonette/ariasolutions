"""Tests for the wholeness tool — Aria's integrated self-knowledge (T0, advisory)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


def _tool():
    from sovereign_agent.tools.wholeness_tool import WholenessTool
    return WholenessTool()


def _run(coro):
    return asyncio.run(coro)


def test_wholeness_is_t0_readonly():
    t = _tool()
    assert t.tier == 0
    assert "read_error" in t.failure_modes


def test_wholeness_runs_and_is_advisory():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok
    assert res.output["advisory"] is True
    assert "confidence_statement" in res.output


def test_wholeness_fuses_classical_and_nonclassical():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    out = res.output
    assert "classical" in out and "non_classical" in out and "maturity" in out
    # non-classical globe present with 13 nodes
    if out["non_classical"].get("node_count"):
        assert out["non_classical"]["node_count"] == 13


def test_wholeness_includes_maturity_spectrums():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    mat = res.output["maturity"]
    if mat.get("ego"):
        assert mat["ego"]["advisory"] is True
        assert mat["institutional_impulse"]["advisory"] is True


def test_wholeness_confidence_statement_is_string():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert isinstance(res.output["confidence_statement"], str)
    assert len(res.output["confidence_statement"]) > 0


def test_wholeness_has_depth_guidance():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert "expression_depth_guidance" in res.output
    assert isinstance(res.output["expression_depth_guidance"], str)
