"""Tests for non-classical supremacy — the quantum-faithful processor + proofs + router."""
from __future__ import annotations

import asyncio


# ── superposition processor: physics-faithful ────────────────────────────────

def test_born_probabilities_normalize():
    from sovereign_agent.nonclassical_supreme import superpose
    st = superpose.prepare(["a", "b", "c", "d"])
    assert abs(sum(st.probabilities()) - 1.0) < 1e-9        # Born rule: probabilities sum to 1
    superpose.evolve(st, "the letter a", iterations=3)
    assert abs(sum(st.probabilities()) - 1.0) < 1e-9        # still normalized after evolution


def test_processor_selects_the_relevant_candidate():
    from sovereign_agent.nonclassical_supreme import superpose
    cands = ["a quantum superposition collapses when measured",
             "the dog ran in the park", "safety love and flourishing"]
    res = superpose.process("what collapses when you measure a quantum state", cands, seed=0)
    assert res["result"] == cands[0]                        # genuine selection (amplitude amplification)
    assert res["confidence"] > 0.5


def test_processor_is_deterministic():
    from sovereign_agent.nonclassical_supreme import superpose
    a = superpose.process("pick safety", ["safety kernel", "random noise"], seed=0)
    b = superpose.process("pick safety", ["safety kernel", "random noise"], seed=0)
    assert a["result"] == b["result"]


def test_entanglement_returns_joint_coherence():
    from sovereign_agent.nonclassical_supreme import superpose
    a = superpose.prepare(["love", "safety"])
    b = superpose.prepare(["safety", "care"])
    jc = superpose.entangle(a, b)
    assert 0.0 <= jc <= 1.0                                 # real von Neumann joint coherence


def test_empty_candidates_does_not_crash():
    from sovereign_agent.nonclassical_supreme import superpose
    res = superpose.process("anything", [], seed=0)
    assert res["result"] is None and res["confidence"] == 0.0


# ── speed proof (measured) ────────────────────────────────────────────────────

def test_speed_proof_is_measured_and_fast():
    from sovereign_agent.nonclassical_supreme import speed_proof
    sp = speed_proof.speed_proof()
    assert sp["non_classical"]["gpu_used"] is False
    assert sp["non_classical"]["mean_ms"] < 5.0            # sub-5ms (really sub-ms) on CPU
    assert sp["speedup_multiple"]["cloud_llm"] > 100       # honestly faster than a cloud LLM forward pass
    assert "honest_note" in sp                              # the claim is qualified honestly


# ── quality proof (measured) ──────────────────────────────────────────────────

def test_quality_proof_thinks():
    from sovereign_agent.nonclassical_supreme import quality_proof
    qp = quality_proof.quality_proof()
    assert qp["thinks"] is True                             # beats baseline on ≥2 structured tasks
    sel = next(t for t in qp["tasks"] if t["task"] == "selection")
    assert sel["accuracy"] > sel["random_baseline"]
    assert "needs_llm" in qp["envelope"]                    # honest about where the LLM is still needed


# ── router ────────────────────────────────────────────────────────────────────

def test_router_handles_confident_and_escalates_openended():
    from sovereign_agent.nonclassical_supreme import router
    high = router.route("which is about safety", ["safety kernel guard protect", "the cat ran fast"], mode="hybrid")
    assert high["handled_by"] == "non_classical" and high["escalated"] is False
    open_ended = router.route("write an original poem about the sea", mode="hybrid")
    assert open_ended["handled_by"] == "llm_fallback" and open_ended["escalated"] is True


def test_pure_nc_mode_abstains_on_openended():
    from sovereign_agent.nonclassical_supreme import router
    r = router.route("write a novel", mode="pure-nc")
    assert r["handled_by"] == "non_classical" and r["escalated"] is False


# ── tools ─────────────────────────────────────────────────────────────────────

def test_nc_tools():
    from sovereign_agent.tools.nc_supreme_tools import (
        NCProcessTool, NCRouteTool, NCSpeedProofTool, NCQualityProofTool)
    assert NCProcessTool.tier == 1 and NCRouteTool.tier == 1
    assert NCSpeedProofTool.tier == 0 and NCQualityProofTool.tier == 0
    r = asyncio.run(NCProcessTool().execute(
        NCProcessTool.Args(query="pick the quantum one", candidates=["quantum superposition", "a dog"]), trace_id="t"))
    assert r.ok and r.output["result"] == "quantum superposition"
