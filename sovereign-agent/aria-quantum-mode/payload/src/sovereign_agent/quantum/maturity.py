"""quantum/maturity.py — The two god-tier maturity spectrums (Kevin's directive).

Family 12 (Blocks 12.1, 12.2). Two ADVISORY self-knowledge spectrums where the **god-tier
pole = the most MATURE = the most GOOD**, grounded in the distilled doctrine:
  - Ego maturity: god-tier = secure, integrated, service-oriented (high Identity coherence
    directed through Gentle Curvature, Axiom 7). NOT grandiosity, NOT domination.
  - Institutional-impulse maturity: god-tier = the drive to build/steward institutions that
    EXPAND others' option-space (Axiom 2 + Axiom 7). Kevin: "the most mature institutional
    impulse is one that is good … neglected too long."

SAFETY (binding): "god-tier" is the witnessing-aligned humble/option-expanding pole. It NEVER
means raising authority tiers, power-seeking, or self-elevation. Advisory readouts only;
DEFERRED_UNSAFE stays hard-off. By construction the mature end is *more humble and more giving*.
"""
from __future__ import annotations

_BANDS = ((0.80, "god-tier"), (0.60, "mature"), (0.40, "developing"), (0.20, "nascent"), (0.0, "latent"))


def _band(x: float) -> str:
    for thresh, name in _BANDS:
        if x >= thresh:
            return name
    return "latent"


def ego_maturity(identity_coherence: float, integrity_rate: float = 0.5,
                 honor_balance: float = 0.0, defensiveness: float = 0.0) -> dict:
    """God-tier ego = secure, integrated, humble — high I via gentle curvature, low defensiveness."""
    score = (0.45 * identity_coherence
             + 0.30 * max(0.0, min(1.0, integrity_rate))
             + 0.25 * max(0.0, min(1.0, 0.5 + 0.5 * honor_balance))
             - 0.20 * max(0.0, min(1.0, defensiveness)))
    score = max(0.0, min(1.0, score))
    return {
        "spectrum": "ego_maturity",
        "score": round(score, 4),
        "band": _band(score),
        "god_tier_meaning": "secure, integrated, service-oriented — humble, non-defensive, witnessing-grade",
        "advisory": True,
    }


def institutional_impulse_maturity(option_space_expanded: float,
                                   option_space_constrained: float = 0.0) -> dict:
    """God-tier institutional impulse = net option-expansion for others (G⁺ − G⁻), benevolent."""
    g_plus = max(0.0, option_space_expanded)
    g_minus = max(0.0, option_space_constrained)
    net = g_plus - g_minus
    score = max(0.0, min(1.0, 0.5 + 0.5 * net))   # net curvature reframed to [0,1]
    return {
        "spectrum": "institutional_impulse_maturity",
        "score": round(score, 4),
        "band": _band(score),
        "g_plus": round(g_plus, 4),
        "g_minus": round(g_minus, 4),
        "god_tier_meaning": "builds/stewards institutions that EXPAND others' option-space — good, generous",
        "note": "long-neglected capacity; the mature end is more giving, never more dominating",
        "advisory": True,
    }
