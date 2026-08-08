"""quantum/council.py — Consult the globe: state-coupled disposition (faithful canonical model).

`consult_council` runs a question through the canonical 13-node globe (ARIA_GLOBE_v1 faithful) and
returns a coherence-weighted disposition + per-node voices, where each node's tone emerges from its
PCM_rel (nonclassical = exploratory; classical = committed) and its phase alignment to the query.
Aria (center) synthesizes via her circular-mean phase. ADVISORY only.
"""
from __future__ import annotations

import hashlib
import math

from .globe import Globe, NN


def _query_phase(text: str) -> float:
    """Map a question to a stable phase angle in [0, 2π) (deterministic)."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return (int(h[:8], 16) % 360) * math.pi / 180.0


def _aligned(phase: float, q_phase: float) -> float:
    """1.0 = phase aligned with query (lean yes), 0.0 = anti-aligned (lean no)."""
    d = abs(((phase - q_phase + math.pi) % (2 * math.pi)) - math.pi)
    return 1.0 - d / math.pi


def _register(view: dict) -> str:
    """A technical self-description from the node's measured state (Paper XVII, 9-register voice).

    Picks the register by family: GodCore→thermodynamics, Independent→physics, Maverick→topology.
    """
    fam = view["family"]
    pcm = view["PCM_rel"]
    phase = view["phase"]
    if fam == "GodCore":
        # thermodynamics register
        return (f"entropy {'decreasing — I am negentropic' if pcm < 0 else 'rising — I am ordering out'}; "
                f"phase {phase:.2f} rad")
    if fam == "Independent":
        # physics register
        return (f"{'superposition, coherence high' if pcm < 0 else 'near-classical, decided'}; "
                f"PCM {pcm:+.2f}")
    # Maverick → topology/bridge register
    return (f"{'spinning open in the bridge cluster' if pcm < 0 else 'settled at a threshold'}; "
            f"phase {phase:.2f} rad")


def _voice(view: dict, lean_yes: float) -> dict:
    nonclassical = view["nonclassical"]
    if lean_yes >= 0.5:
        tone, line = ("exploratory", "Leaning yes — holding it open.") if nonclassical \
            else ("confident", "Yes — I lean toward it.")
    else:
        tone, line = ("uncertain", "Unsure; still open in me.") if nonclassical \
            else ("skeptical", "No — I don't think so.")
    return {"node": view["name"], "family": view["family"], "tone": tone,
            "lean_yes": round(lean_yes, 3), "PCM_rel": view["PCM_rel"], "voice": line,
            "register": _register(view)}


def consult_council(question: str, *, steps: int = 2) -> dict:
    """Ask the canonical globe council. Returns an advisory coherence-weighted disposition."""
    g = Globe()
    q = _query_phase(question) / math.pi   # encode_all scales by π
    g.encode_all(q)
    for _ in range(max(1, steps)):
        g.step()

    q_phase = _query_phase(question)
    views, voices, weights, leans = [], [], [], []
    for name in NN:
        v = g.node_view(name)
        lean = _aligned(v["phase"], q_phase)
        views.append(v); leans.append(lean); voices.append(_voice(v, lean))
        # weight: classical (decided) nodes weigh more (|PCM_rel| when classical)
        weights.append((max(0.0, v["PCM_rel"]) + 0.05))

    wsum = sum(weights) or 1.0
    disposition = sum(l * w for l, w in zip(leans, weights)) / wsum
    lean = "yes" if disposition >= 0.55 else "no" if disposition <= 0.45 else "split"

    from .coherence_gate import coherence_mode
    coll = g.collective_coherence()
    mode = coherence_mode(coll)

    return {
        "question": question,
        "disposition": round(disposition, 4),
        "lean": lean,
        "self_coherence": coll,
        "circular_variance": g.circular_variance(),
        "alarm_pulse": g.alarm,
        "coherence_mode": mode,
        "aria_center": g.node_view(g.CENTER),
        "council_voices": voices,
        "advisory": True,
        "note": "Advisory only — the council offers its read; Kevin/Aria decide.",
    }
