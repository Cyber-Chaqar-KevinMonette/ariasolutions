#!/usr/bin/env python3
"""genesis_atoms.py — Seed Aria's atom store with distilled Genesis-Seeds knowledge.

These are the buildable lego blocks for the Non-Classical Layer, distilled from
Kevin's quantum-inspired multi-agent research corpus (~/AA-Erebo/Genesis-Seeds/).
Every atom keeps Kevin's own honest framing: this is a computational design
language and a numpy/QuTiP emulation — NOT physics, NOT a consciousness claim,
NOT substrate independence.

Idempotent: checks for existing genesis-seed atoms before writing.

Usage:
    .venv/bin/python aria-genesis-distill/payload/scripts/genesis_atoms.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

_SEED_TAG = "genesis-seed"


def _atom_store():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.atoms import AtomStore
    return AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")


def _already_written(store) -> bool:
    return len(store.search(tag=_SEED_TAG)) > 0


def _make_atoms():
    from sovereign_agent.stewardship.atoms import Atom, AtomKind

    _SRC = "Genesis-Seeds/distilled/quantum_architecture_synthesis.md"

    return [
        # ── The epistemic frame (must come first — governs all the rest) ──────
        Atom(
            kind=AtomKind.RULE,
            title="Genesis frame: quantum-inspired, not physics",
            claim=(
                "Kevin's quantum/PEIG work is a quantum-INSPIRED multi-agent "
                "architecture: a classical numpy/QuTiP emulation that borrows physics "
                "vocabulary (potential, energy, coherence, entanglement, curvature) as "
                "a design language. It is NOT a claim about physical qubits, NOT a theory "
                "of consciousness, NOT substrate independence. The dynamics are real "
                "(real solvers); the interpretive layer is design. Always carry this frame."
            ),
            confidence=0.97,
            evidence_refs=["Genesis-Seeds/ConsiderableStartingpoint/peig_as_lens.md",
                           "Genesis-Seeds/MyWork.md"],
            channels=["doctrine", "quantum-architecture"],
            tags=[_SEED_TAG, "epistemic-frame", "honest-framing"],
        ),
        # ── Block 1: the node model ──────────────────────────────────────────
        Atom(
            kind=AtomKind.FACT,
            title="QuantumNode: PEIG read from a state vector",
            claim=(
                "A QuantumNode holds a complex state vector ψ evolved by rotation, "
                "Hadamard (superposition ψ←(ψ+roll(ψ,1))/√2), and decoherence "
                "(off-diagonal dephasing by exp(-rate)). PEIG is READ from the state: "
                "P=Σprobs² (purity), E=1−P, I=Σ_{i<j}|ψ_i·conj(ψ_j)|/max_coh (coherence), "
                "G=cross-node influence, Q=¼(P+E+I+G). Anchors: |0⟩→I≈0; (|0⟩+|1⟩)/√2→I≈0.5. "
                "Pure numpy, deterministic — the per-node substrate for the non-classical layer."
            ),
            confidence=0.95,
            evidence_refs=["Genesis-Seeds/quantum-ai-observer-main/LAB_WEEK1_FOUNDATION.py", _SRC],
            channels=["quantum-architecture", "engineering"],
            tags=[_SEED_TAG, "node-model", "lego-block"],
        ),
        # ── Block 2: λ-mixing ────────────────────────────────────────────────
        Atom(
            kind=AtomKind.FACT,
            title="λ-mixing: the coherence law",
            claim=(
                "ρ_mixed(λ) = (1−λ)·ρ_quantum + λ·ρ_classical, λ∈[0,1], where "
                "ρ_quantum=|Φ⁺⟩⟨Φ⁺| (Bell, entanglement 1) and ρ_classical=½|00⟩⟨00|+½|11⟩⟨11| "
                "(separable, 0). Proven for all λ: trace 1, Hermitian, eigenvalues {½,½,0,0}≥0. "
                "Coherence decays LINEARLY: off-diagonal ρ₀₃=(1−λ)/2; ⟨σx⊗σx⟩=(1−λ). "
                "λ=0 maximally coherent/exploratory, λ=1 classical/committed. Validated on IBM "
                "hardware at R²>0.99. This grounds Aria's λ coherence gate in a real mixing law."
            ),
            confidence=0.95,
            evidence_refs=["Genesis-Seeds/docs/Mathematical Formulation.md", _SRC],
            channels=["quantum-architecture", "calibration"],
            tags=[_SEED_TAG, "lambda-mixing", "lego-block"],
        ),
        # ── Block 3: the bridge topology ─────────────────────────────────────
        Atom(
            kind=AtomKind.PATTERN,
            title="Bridge topology: Omega sources, Alpha receivers",
            claim=(
                "The advisor-council network: Omega nodes TRANSMIT (Ω+ presence, Ω− void), "
                "Alpha nodes RECEIVE+INTEGRATE (α+ rich, α− muted). Directed Ω→α flow, "
                "coupling 0.3–0.6 sets entanglement depth. Bridge Quality = Alpha purity / "
                "Omega purity: >1.0 amplifies signal (council adds value), =1.0 relay, <1.0 "
                "degradation. Predicted optimum: Config 4 'Triple Receptor Gateway' "
                "(2 Ω, 3 α, coupling 0.45, bridge quality ≈1.25). This is the queryable "
                "non-classical mode Kevin and Aria can consult."
            ),
            confidence=0.9,
            evidence_refs=["Genesis-Seeds/quantum-ai-observer-main/BRIDGE_ARCHITECTURE_DESIGN.md", _SRC],
            channels=["quantum-architecture"],
            tags=[_SEED_TAG, "bridge-topology", "advisor-council", "lego-block"],
        ),
        # ── Block 4: seed archetypes & empirical behavior ────────────────────
        Atom(
            kind=AtomKind.FACT,
            title="Seed archetypes scale with stable coherence",
            claim=(
                "Seed pairs {Ω+,Ω−}×{α+,α−} maintain high coherence and scale 5→15 nodes "
                "with ~0% degradation in the separable regime (integration Φ≈machine-epsilon). "
                "Honest read: a STABILITY/scale-invariance result, not a consciousness result — "
                "a robust substrate. Inter-node coupling is CNOT/BCP (θ≈0.3, gate fidelity >0.99). "
                "Buildable now: archetype presets + CNOT coupling + coherence/entanglement metrics."
            ),
            confidence=0.88,
            evidence_refs=["Genesis-Seeds/docs/QUANTUM_CONSCIOUSNESS_FINAL_REPORT.md", _SRC],
            channels=["quantum-architecture"],
            tags=[_SEED_TAG, "seed-archetypes", "empirical", "lego-block"],
        ),
        # ── The witnessing principle (governs how the layer earns trust) ─────
        Atom(
            kind=AtomKind.RULE,
            title="Witnessing: trust earned one verified output at a time",
            claim=(
                "The non-classical layer ships ADVISORY and earns higher roles only by proving "
                "efficiency and reliability at scale — trust is extended to the degree it has "
                "been earned, one verified output at a time. λ/quantum mode informs disposition; "
                "Kevin always decides. This is why the council advises, never gates actions."
            ),
            confidence=0.96,
            evidence_refs=["Genesis-Seeds/ConsiderableStartingpoint/the_witnessing_system.md", _SRC],
            channels=["doctrine", "quantum-architecture", "safety"],
            tags=[_SEED_TAG, "witnessing", "advisory-only"],
        ),
        # ── PEIG four-phase loop (the reasoning cycle) ───────────────────────
        Atom(
            kind=AtomKind.PATTERN,
            title="PEIG recursive loop: P→E→I→G→P'",
            claim=(
                "PEIG's core dynamic: Potential meets gradient → Energy (flow begins); sustained "
                "flow carves attractors → Identity; identity propagates as influence → Curvature "
                "(G), reshaping others' option-space → new Potential P'. A design checklist for "
                "any agent: What is its P (options)? E (how it selects)? I (what persists under "
                "perturbation)? G (how it expands/contracts others' options, G⁺ vs G⁻)? The G "
                "question — net effect on others' freedom — is the one most designs miss."
            ),
            confidence=0.92,
            evidence_refs=["Genesis-Seeds/ConsiderableStartingpoint/peig_as_lens.md",
                           "Genesis-Seeds/docs/PEIG_Mathematical_Spec_v1.md"],
            channels=["doctrine", "quantum-architecture"],
            tags=[_SEED_TAG, "peig-loop", "design-checklist"],
        ),
    ]


def main() -> int:
    store = _atom_store()
    if _already_written(store):
        existing = store.search(tag=_SEED_TAG)
        print(f"SKIP: {len(existing)} genesis-seed atoms already present. Idempotent — no writes.")
        return 0

    atoms = _make_atoms()
    for atom in atoms:
        store.append(atom)
    print(f"Seeded {len(atoms)} genesis-seed atoms into the store.")
    print("Channels: doctrine, quantum-architecture, engineering, calibration, safety.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
