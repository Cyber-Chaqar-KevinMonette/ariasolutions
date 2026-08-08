"""quantum/coherence_gate.py — λ coherence gate (advisory mode selector).

Distilled from the λ-mixing law (Block 2.1) and Landauer "cost of agency" (Block 10.5).
ρ_mixed(λ) = (1−λ)ρ_quantum + λρ_classical. λ low = exploratory/coherent (hold candidates,
reversible — thermodynamically free); λ high = committed/classical (decide, irreversible —
pays the Landauer cost). Advisory only: notes the mode; Kevin always decides.
"""
from __future__ import annotations

_EXPLORATORY = 0.35
_COMMITTED = 0.65


def lambda_from_globe(collective_coherence: float, energy: float = 0.5) -> float:
    """Derive advisory λ from globe coherence + energy. High coherence → low λ (exploratory)."""
    lam = 0.6 * energy + 0.4 * (1.0 - collective_coherence)
    return max(0.0, min(1.0, lam))


def band(lam: float) -> str:
    if lam < _EXPLORATORY:
        return "exploratory"
    if lam >= _COMMITTED:
        return "committed"
    return "adaptive"


def coherence_mode(collective_coherence: float, energy: float = 0.5) -> dict:
    """Advisory coherence-mode readout with the cost-of-agency framing."""
    lam = lambda_from_globe(collective_coherence, energy)
    b = band(lam)
    cost_note = {
        "exploratory": "hold multiple candidate paths — reversible, low agency-cost (Landauer-free)",
        "adaptive": "narrowing — weigh whether the value of deciding exceeds its cost",
        "committed": "decide decisively — irreversible collapse, pays the cost of agency",
    }[b]
    return {
        "lambda": round(lam, 4),
        "band": b,
        "guidance": cost_note,
        "advisory": True,
    }
