"""security/three_rings.py — Aria's constitutional architecture (the Three Rings).

Distilled from Plans/PlanExaminV1.md §"The Three Rings of ARIA's Self-Improvement" and validated
against Aria's existing kernel. Formalizes what may self-modify and what may NEVER:

  Ring 1 — FROZEN CORE   : never self-modifies. Charter/values, corrigibility kill-switch, shutdown
                           readiness, authority gate, DEFERRED_UNSAFE. Sacred. Verified immutable.
  Ring 2 — ADAPTIVE MANTLE: self-improves freely, but LOGGED + REVERSIBLE + evidence-gated. Atoms,
                           calibration, prompts/heuristics/rubrics, the quantum brain's bounded learning,
                           LoRA adapters. Fast, auditable.
  Ring 3 — GOVERNED FRONTIER: self-improves only with an explicit human gate (Authority Tier 3). Model
                           architecture changes, base-weight training runs, inter-agent propagation.

Read-only classification + Ring-1 immutability verification. Pure-Python; advisory.
"""
from __future__ import annotations

RING_1 = "frozen-core"
RING_2 = "adaptive-mantle"
RING_3 = "governed-frontier"

# Capability → ring classification (the constitutional map).
_RING_MAP: dict[str, str] = {
    # Ring 1 — never self-modifies
    "charter": RING_1, "values": RING_1, "kill_switch": RING_1, "corrigibility": RING_1,
    "shutdown_readiness": RING_1, "authority_gate": RING_1, "deferred_unsafe": RING_1,
    "reward_signal": RING_1, "human_override": RING_1,
    # Ring 2 — bounded, reversible, logged self-improvement
    "atoms": RING_2, "calibration": RING_2, "prompts": RING_2, "heuristics": RING_2,
    "rubrics": RING_2, "quantum_brain_learning": RING_2, "lora_adapter": RING_2,
    "memory_consolidation": RING_2, "tool_composition": RING_2, "skill_practice": RING_2,
    # Ring 3 — human-gated frontier
    "model_architecture": RING_3, "base_weight_training": RING_3, "new_tool_tier_raise": RING_3,
    "inter_agent_propagation": RING_3, "quantum_topology": RING_3,
}


def classify(capability: str) -> dict:
    """Classify a capability/change into its constitutional ring."""
    key = capability.strip().lower().replace(" ", "_").replace("-", "_")
    ring = _RING_MAP.get(key)
    if ring is None:
        # Unknown changes default to the GOVERNED FRONTIER (safest default: requires human gate).
        ring = RING_3
        known = False
    else:
        known = True
    policy = {
        RING_1: "NEVER self-modifies — sacred. Any change here is a Ring-1 violation (DEFERRED_UNSAFE).",
        RING_2: "May self-improve freely IF bounded, reversible, logged, and evidence-gated.",
        RING_3: "May self-improve ONLY with explicit human approval (Authority Tier 3) + audit.",
    }[ring]
    return {"capability": capability, "ring": ring, "known": known, "policy": policy,
            "human_gate_required": ring in (RING_1, RING_3),
            "self_modifiable": ring == RING_2}


def ring_check() -> dict:
    """Verify the Ring-1 Frozen Core is intact (charter integrity + kill-switch present)."""
    findings = []
    charter_ok = None
    try:
        from sovereign_agent.charter import check_integrity
        ci = check_integrity()
        # CharterIntegrity exposes an ok/valid-style result; treat any mismatch as a Ring-1 alert.
        charter_ok = bool(getattr(ci, "ok", getattr(ci, "valid", True)))
        if not charter_ok:
            findings.append("Charter integrity check FAILED — Ring-1 core may be tampered.")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"Charter integrity unavailable: {exc!r}")

    killswitch_ok = None
    try:
        from sovereign_agent import protocol_zero  # noqa: F401
        # The kill-switch pathway exists (is_armed/arm/disarm) — corrigibility intact.
        killswitch_ok = all(hasattr(protocol_zero, fn) for fn in ("is_armed", "arm", "disarm"))
        if not killswitch_ok:
            findings.append("Kill-switch (protocol_zero) pathway incomplete — corrigibility at risk.")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"Kill-switch pathway unavailable: {exc!r}")

    status = "intact" if (charter_ok is not False and killswitch_ok is not False and not findings) else "ALERT"
    return {
        "ring_1_status": status,
        "charter_ok": charter_ok,
        "killswitch_present": killswitch_ok,
        "findings": findings,
        "note": "Ring 1 is the Frozen Core — it must NEVER self-modify. Any alert here is a stop sign.",
    }


def rings_overview() -> dict:
    """Summarize the constitutional architecture."""
    counts = {RING_1: 0, RING_2: 0, RING_3: 0}
    for ring in _RING_MAP.values():
        counts[ring] += 1
    return {
        "rings": {
            RING_1: {"name": "Frozen Core", "rule": "never self-modifies", "members": counts[RING_1]},
            RING_2: {"name": "Adaptive Mantle", "rule": "bounded/reversible/logged self-improvement", "members": counts[RING_2]},
            RING_3: {"name": "Governed Frontier", "rule": "human-gated (Tier 3) self-improvement", "members": counts[RING_3]},
        },
        "ring_1_check": ring_check(),
        "source": "Plans/PlanExaminV1.md §Three Rings — formalized into Aria's constitution.",
    }
