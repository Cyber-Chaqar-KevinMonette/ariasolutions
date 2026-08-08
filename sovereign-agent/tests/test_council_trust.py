"""Tests for the council trust ledger (witnessing track record)."""
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


def _trust():
    from sovereign_agent.quantum import trust
    return trust


# ── ledger logic ──────────────────────────────────────────────────────────────

def test_log_and_calibration_empty(tmp_path):
    t = _trust()
    cal = t.calibration(tmp_path)
    assert cal["total_consults"] == 0
    assert cal["trust_band"] == "unproven"


def test_log_consult_then_record_correct(tmp_path):
    t = _trust()
    e = t.log_consult(tmp_path, question="Ship it?", lean="yes", disposition=0.8, coherence=0.9)
    cid = e["consult_id"]
    r = t.record_outcome(tmp_path, consult_id=cid, outcome="yes")
    assert r["ok"] is True
    assert r["correct"] is True
    cal = t.calibration(tmp_path)
    assert cal["scored"] == 1 and cal["correct"] == 1


def test_record_wrong_lowers_accuracy(tmp_path):
    t = _trust()
    e = t.log_consult(tmp_path, question="Do X?", lean="no", disposition=0.3, coherence=0.8)
    t.record_outcome(tmp_path, consult_id=e["consult_id"], outcome="yes")  # council said no, reality yes
    cal = t.calibration(tmp_path)
    assert cal["correct"] == 0 and cal["accuracy"] == 0.0


def test_split_lean_not_scored(tmp_path):
    t = _trust()
    e = t.log_consult(tmp_path, question="Maybe?", lean="split", disposition=0.5, coherence=0.7)
    r = t.record_outcome(tmp_path, consult_id=e["consult_id"], outcome="yes")
    assert r["correct"] is None
    cal = t.calibration(tmp_path)
    assert cal["scored"] == 0   # split leans are neutral


def test_trust_band_needs_five_scored(tmp_path):
    t = _trust()
    for i in range(6):
        e = t.log_consult(tmp_path, question=f"q{i}", lean="yes", disposition=0.8, coherence=0.9)
        t.record_outcome(tmp_path, consult_id=e["consult_id"], outcome="yes")
    cal = t.calibration(tmp_path)
    assert cal["scored"] == 6 and cal["trust_band"] == "trusted"


def test_record_unknown_id(tmp_path):
    t = _trust()
    r = t.record_outcome(tmp_path, consult_id="C-doesnotexist", outcome="yes")
    assert r["ok"] is False and "not_found" in r["error"]


# ── tools ─────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_calibration_tool_t0():
    from sovereign_agent.tools.council_trust_tools import CouncilCalibrationTool
    t = CouncilCalibrationTool()
    assert t.tier == 0
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok and "trust_band" in res.output


def test_record_outcome_tool_t1_validates():
    from sovereign_agent.tools.council_trust_tools import CouncilRecordOutcomeTool
    t = CouncilRecordOutcomeTool()
    assert t.tier == 1
    res = _run(t.execute(t.Args(consult_id="C-nope", outcome="maybe"), trace_id="t"))
    assert not res.ok


def test_quantum_consult_returns_consult_id():
    # after the patch, quantum_consult auto-logs and returns a consult_id
    from sovereign_agent.tools.quantum_consult_tool import QuantumConsultTool
    t = QuantumConsultTool()
    res = _run(t.execute(t.Args(question="Is the trust ledger wired?"), trace_id="t"))
    assert res.ok
    assert "consult_id" in res.output
