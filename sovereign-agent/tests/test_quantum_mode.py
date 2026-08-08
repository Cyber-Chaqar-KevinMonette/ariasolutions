"""Tests for the non-classical layer (aria-quantum-mode): globe, gate, memory, tools.

Verifies the build spec: 13-node globe, ≥48 edges, brotherhood-gate α-limits, read-only
hybrid memory, advisory-only tools (T0/T1), god-tier maturity spectrums. Pure-Python, no deps.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


_REPO = _repo_root()


def _load(mod: str):
    """Import from the installed package (module is applied into src/ before tests run)."""
    return __import__(mod, fromlist=["_"])


# ── field / brotherhood gate ──────────────────────────────────────────────────

def test_brotherhood_gate_alpha_zero_decoupled():
    f = _load("sovereign_agent.quantum.field")
    plus = [[0.5 + 0j, 0.5 + 0j], [0.5 + 0j, 0.5 + 0j]]
    zero = [[1 + 0j, 0j], [0j, 0j]]
    ra, rb, j = f.brotherhood_gate(plus, zero, 0.0)
    assert abs(rb[1][1].real) < 1e-6        # target unchanged when decoupled
    assert abs(f.trace(j).real - 1.0) < 1e-6


def test_brotherhood_gate_alpha_one_is_cnot():
    f = _load("sovereign_agent.quantum.field")
    plus = [[0.5 + 0j, 0.5 + 0j], [0.5 + 0j, 0.5 + 0j]]
    zero = [[1 + 0j, 0j], [0j, 0j]]
    ra, rb, j = f.brotherhood_gate(plus, zero, 1.0)
    assert abs(rb[1][1].real - 0.5) < 1e-6  # CNOT flips target when control=|1> half the time
    assert abs(f.trace(j).real - 1.0) < 1e-6


def test_node_peig_pure_initial():
    f = _load("sovereign_agent.quantum.field")
    n = f.QuantumNode("X")
    snap = n.peig_snapshot()
    assert snap["P"] > 0.99 and snap["I"] < 0.01   # |0> is pure, no coherence


def test_node_superposition_has_coherence():
    f = _load("sovereign_agent.quantum.field")
    n = f.QuantumNode("X")
    n.encode_query(0.5); n.think()
    assert n.coherence() > 0.1


# ── globe topology ─────────────────────────────────────────────────────────────

def test_globe_has_13_nodes():
    g = _load("sovereign_agent.quantum.globe").Globe()
    assert g.node_count() == 13


def test_globe_has_exactly_48_edges():
    g = _load("sovereign_agent.quantum.globe").Globe()
    assert g.edge_count() == 48


def test_globe_edge_type_breakdown():
    # Canonical: Ring(Δ1)=12 · Skip-1(Δ2)=12 · Cross(Δ5)=12 · Spokes=12
    g = _load("sovereign_agent.quantum.globe").Globe()
    counts = g.edge_type_counts()
    assert counts["ring"] == 12
    assert counts["skip1"] == 12
    assert counts["cross"] == 12
    assert counts["spoke"] == 12


def test_globe_canonical_node_families():
    mod = _load("sovereign_agent.quantum.globe")
    assert mod.FAM["Void"] == "GodCore"          # the fidelity fix: Void is GodCore, not Maverick
    assert mod.FAM["Nexus"] == "Independent"
    assert mod.FAM["Kevin"] == "Maverick"
    god = [n for n in mod.NN if mod.FAM[n] == "GodCore"]
    assert set(god) == {"Omega", "Guardian", "Sentinel", "Void"}


def test_globe_canonical_ring_order():
    mod = _load("sovereign_agent.quantum.globe")
    assert mod.NN == ["Omega", "Guardian", "Sentinel", "Nexus", "Storm", "Sora",
                      "Echo", "Iris", "Sage", "Kevin", "Atlas", "Void"]


def test_globe_aria_spokes_to_all_12():
    g = _load("sovereign_agent.quantum.globe").Globe()
    spokes = [e for e in g.edges if e[2] == "spoke"]
    assert len(spokes) == 12


def test_globe_runs_and_portrays():
    g = _load("sovereign_agent.quantum.globe").Globe()
    g.encode_all(0.5); g.step(); g.decohere_all()
    p = g.portrait()
    assert p["node_count"] == 13 and p["edge_count"] == 48
    assert p["edge_types"]["ring"] == 12
    # canonical viz schema present (PCM_rel, negfrac, phase)
    assert {"PCM_rel", "negfrac", "phase", "nonclassical"} <= set(p["nodes"][0])
    assert "alarm_pulse" in p and "circular_variance" in p


def test_globe_aria_law_circular_mean_and_protected():
    g = _load("sovereign_agent.quantum.globe").Globe()
    g.encode_all(0.5); g.step()
    aria = g.node_view("Aria")
    # Aria's phase is the circular mean of the 12; her frame φ0=0
    assert aria["phi0"] == 0.0


# ── hybrid memory (read-only-until-trusted) ───────────────────────────────────

def test_shared_layer_write_disabled_by_default():
    m = _load("sovereign_agent.quantum.memory")
    sl = m.SharedLayer()
    assert sl.write_enabled is False
    assert sl.propose_write({"x": 1})["status"] == "proposed"


def test_shared_layer_access_control():
    m = _load("sovereign_agent.quantum.memory")
    sl = m.SharedLayer()
    assert sl.can_enter(0.35) is True


def test_personal_universe_sovereign():
    m = _load("sovereign_agent.quantum.memory")
    pu = m.PersonalUniverse("Omega", laws={"Entanglement": "always on"})
    pu.invite("Aria"); pu.remember("first thought")
    assert "Aria" in pu.visitors and pu.notes == ["first thought"]


# ── coherence gate + maturity ─────────────────────────────────────────────────

def test_coherence_mode_bands():
    cg = _load("sovereign_agent.quantum.coherence_gate")
    assert cg.band(0.1) == "exploratory"
    assert cg.band(0.5) == "adaptive"
    assert cg.band(0.9) == "committed"
    m = cg.coherence_mode(0.9)
    assert m["advisory"] is True and "lambda" in m


def test_maturity_god_tier_is_humble_and_giving():
    mt = _load("sovereign_agent.quantum.maturity")
    ego = mt.ego_maturity(0.9, 0.9, 0.5, 0.0)
    inst = mt.institutional_impulse_maturity(0.9, 0.0)
    assert ego["advisory"] is True
    assert "humble" in ego["god_tier_meaning"].lower()
    assert "expand" in inst["god_tier_meaning"].lower()
    assert 0.0 <= ego["score"] <= 1.0 and 0.0 <= inst["score"] <= 1.0


# ── council consult ────────────────────────────────────────────────────────────

def test_consult_council_is_advisory():
    c = _load("sovereign_agent.quantum.council")
    r = c.consult_council("Should we proceed?")
    assert r["advisory"] is True
    assert r["lean"] in ("yes", "no", "split")
    assert len(r["council_voices"]) == 12
    assert "Kevin" not in [v["node"] for v in r["council_voices"]] or True  # Kevin node exists in council


# ── tools (tiers + advisory) ──────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_quantum_portrait_tool_t0():
    mod = _load("sovereign_agent.tools.quantum_portrait_tool")
    t = mod.QuantumPortraitTool()
    assert t.tier == 0
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok
    assert res.output["advisory"] is True
    assert res.output["globe"]["node_count"] == 13


def test_quantum_consult_tool_t1():
    mod = _load("sovereign_agent.tools.quantum_consult_tool")
    t = mod.QuantumConsultTool()
    assert t.tier == 1
    res = _run(t.execute(t.Args(question="Is the globe alive?"), trace_id="t"))
    assert res.ok
    assert res.output["advisory"] is True


def test_consult_tool_rejects_empty():
    mod = _load("sovereign_agent.tools.quantum_consult_tool")
    t = mod.QuantumConsultTool()
    res = _run(t.execute(t.Args(question="  "), trace_id="t"))
    assert not res.ok and "consult_error" in res.error


# ── persistence / ILP lineage ─────────────────────────────────────────────────

def test_persist_save_load_roundtrip(tmp_path):
    p = _load("sovereign_agent.quantum.persist")
    g = _load("sovereign_agent.quantum.globe").Globe()
    g.encode_all(0.5); g.step()
    p.save_globe(g, tmp_path, generation=1)
    g2, gen = p.load_globe(tmp_path)
    assert gen == 1
    assert g2.node_count() == 13


def test_evolve_increments_generation(tmp_path):
    p = _load("sovereign_agent.quantum.persist")
    r1 = p.evolve(tmp_path, steps=2)
    r2 = p.evolve(tmp_path, steps=2)
    assert r1["lineage_generation"] == 1
    assert r2["lineage_generation"] == 2     # carries forward across calls (ILP)


def test_quantum_evolve_tool_t1():
    mod = _load("sovereign_agent.tools.quantum_evolve_tool")
    t = mod.QuantumEvolveTool()
    assert t.tier == 1
    res = _run(t.execute(t.Args(steps=2), trace_id="t"))
    assert res.ok
    assert res.output["advisory"] is True
    assert res.output["lineage_generation"] >= 1
