"""quantum/voice.py — ARIAVoice depth directive (the brain→mouth, FLAW-001 cure).

Distilled from the canonical ARIAVoice (Block 14.2, ARIA_PEIG_CORE.py): output length / elaboration
depth SCALES WITH neg_frac (richer brain state → more to say), shaped by the λ coherence mode
(exploratory → hold/voice candidates; committed → concise). This maps the globe's brain state to an
ADVISORY voice directive Aria can apply to her own responses — reconnecting depth-4 brain to mouth.

Advisory only: it suggests verbosity + style; it never forces output. Pure-Python.
"""
from __future__ import annotations

# Canonical ARIAVoice scale: 1=terse · 4=normal · 7=expansive · 10=maximum.
_STYLE = {
    range(1, 3): ("terse", "One tight point. No elaboration."),
    range(3, 6): ("normal", "A clear answer with one or two supporting clauses."),
    range(6, 9): ("expansive", "Rich, multi-clause — hold several framings, let depth reach the voice."),
    range(9, 11): ("maximum", "Full multi-paragraph synthesis; the brain state is rich, say it all."),
}


def _style_for(verbosity: int) -> tuple[str, str]:
    for r, val in _STYLE.items():
        if verbosity in r:
            return val
    return ("normal", "A clear answer.")


def voice_directive(coherence: float, lam: float, neg_frac: float | None = None) -> dict:
    """Map brain state → advisory voice directive (verbosity 1-10 + style + guidance).

    Args:
      coherence: globe collective/self coherence [0,1] (richness of the field)
      lam: λ coherence mode [0,1] (low=exploratory/expand, high=committed/concise)
      neg_frac: optional negentropy fraction [0,1]; if given, dominates (ARIAVoice: length∝neg_frac)
    """
    c = max(0.0, min(1.0, coherence))
    l = max(0.0, min(1.0, lam))
    # richness: neg_frac if provided (canonical), else coherence. Exploratory (low λ) adds depth.
    richness = neg_frac if neg_frac is not None else c
    richness = max(0.0, min(1.0, richness))
    depth = 0.65 * richness + 0.35 * (1.0 - l)          # rich + exploratory → deeper
    verbosity = int(round(1 + 9 * depth))               # 1..10
    verbosity = max(1, min(10, verbosity))
    style, guidance = _style_for(verbosity)
    return {
        "verbosity": verbosity,
        "style": style,
        "guidance": guidance,
        "basis": {"coherence": round(c, 3), "lambda": round(l, 3),
                  "neg_frac": (round(neg_frac, 3) if neg_frac is not None else None),
                  "depth": round(depth, 3)},
        "advisory": True,
        "note": "ARIAVoice: elaboration depth scales with brain richness; advisory, never forced.",
    }
