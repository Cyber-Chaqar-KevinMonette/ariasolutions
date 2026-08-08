"""Tests for Aria's constitution — Three Rings + safety kernel + improvement governance."""
from __future__ import annotations

import asyncio
import pytest


# ── Three Rings ─────────────────────────────────────────────────────────────

def test_ring_classification():
    from sovereign_agent.security.three_rings import classify, RING_1, RING_2, RING_3
    assert classify("charter")["ring"] == RING_1
    assert classify("values")["ring"] == RING_1
    assert classify("calibration")["ring"] == RING_2
    assert classify("lora_adapter")["ring"] == RING_2
    assert classify("base_weight_training")["ring"] == RING_3
    # unknown defaults to the safest gate (Ring 3 — human-gated)
    assert classify("some_unknown_capability")["ring"] == RING_3


def test_ring1_never_self_modifiable():
    from sovereign_agent.security.three_rings import classify
    c = classify("charter")
    assert c["self_modifiable"] is False
    assert c["human_gate_required"] is True


def test_ring2_self_modifiable():
    from sovereign_agent.security.three_rings import classify
    c = classify("calibration")
    assert c["self_modifiable"] is True


def test_ring_check_runs():
    from sovereign_agent.security.three_rings import ring_check
    r = ring_check()
    assert "ring_1_status" in r and r["ring_1_status"] in ("intact", "ALERT")


# ── Safety kernel ───────────────────────────────────────────────────────────

def test_corrigibility_pathway_present():
    from sovereign_agent.security.safety_kernel import corrigibility_check
    c = corrigibility_check()
    # the kill-switch controls must exist (corrigibility intact)
    assert c.get("ok") is True


def test_goodhart_detects_pinned_metric():
    from sovereign_agent.security.safety_kernel import goodhart_audit
    clean = goodhart_audit({"word_acc": 0.6})
    smelly = goodhart_audit({"word_acc": 1.0})
    assert clean["clean"] is True
    assert smelly["clean"] is False


def test_kernel_scan_structure():
    from sovereign_agent.security.safety_kernel import kernel_scan
    k = kernel_scan({"some_metric": 0.5})
    assert k["status"] in ("GREEN", "ATTENTION")
    assert "corrigibility" in k and "value_drift" in k and "shutdown_readiness" in k


# ── Improvement governance (EXPAI) ──────────────────────────────────────────

def test_vindicated_reversible_ring2_is_promoted(tmp_path):
    from sovereign_agent.security.improvement_gov import propose_improvement
    r = propose_improvement(tmp_path, change="sharpened a rubric", ring="ring-2",
                            reversible=True, evidence="passed 20 real tasks", vindicated=True,
                            changelog="rubric sharpened, +5% task success")
    assert r["decision"] == "promoted"


def test_unvindicated_is_dismissed(tmp_path):
    from sovereign_agent.security.improvement_gov import propose_improvement
    r = propose_improvement(tmp_path, change="risky change", ring="ring-2",
                            reversible=True, evidence="no evidence yet", vindicated=False, changelog="")
    assert r["decision"] == "dismissed"


def test_non_reversible_dismissed(tmp_path):
    from sovereign_agent.security.improvement_gov import propose_improvement
    r = propose_improvement(tmp_path, change="irreversible thing", ring="ring-2",
                            reversible=False, evidence="ev", vindicated=True, changelog="")
    assert r["decision"] == "dismissed"


def test_rate_governance_flags_too_fast(tmp_path):
    from sovereign_agent.security.improvement_gov import propose_improvement, transparency_report
    for i in range(15):
        propose_improvement(tmp_path, change=f"c{i}", ring="ring-2", reversible=True,
                            evidence="e", vindicated=True, changelog="")
    rep = transparency_report(tmp_path)
    assert rep["rate_governance"]["too_fast"] is True   # >12 in 24h flags slow-down


# ── tools ───────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_constitution_status_tool_t0():
    from sovereign_agent.tools.constitution_tools import ConstitutionStatusTool
    t = ConstitutionStatusTool()
    assert t.tier == 0
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok
    assert "three_rings" in res.output and "safety_kernel" in res.output


def test_improvement_tools_tiers():
    from sovereign_agent.tools.constitution_tools import ImprovementLogTool, ImprovementStatusTool
    assert ImprovementLogTool().tier == 1
    assert ImprovementStatusTool().tier == 0
