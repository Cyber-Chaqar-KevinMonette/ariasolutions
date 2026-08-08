"""foresight/foresight.py — the 14-generation foresight engine.

"Think 14 generations ahead." The MOS canon already scores a 7th-generation check; this extends the
projection to G+1..G+14 for an architectural commitment, scoring intergenerational equity, lock-in,
value-drift risk, and reversibility — then consulting the Ultimate Questions as the far-horizon lens.

Honest by construction: this is STRUCTURED FORESIGHT, not prophecy. It surfaces how a choice compounds,
so a decision that looks fine today but corrodes the future is caught while it's still cheap to change.
Deterministic, propose-only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ultimate_questions as uq

GENERATIONS = 14

# NOTE: stems use \w* (not a trailing \b) so "reversible/irreversible/hardcode/flourishing/stewardship/
# corrigible" all match — a trailing \b would fail before the suffix letters (a real bug we dogfooded out).
_LOCKIN_RE = re.compile(r"\b(permanent\w*|irreversib\w*|forever|hard[-\s]?cod\w*|cannot\s+be\s+undone|locked[-\s]in)\b", re.I)
_REVERSIBLE_RE = re.compile(r"\b(reversib\w*|rollback\w*|stag(?:e|ed|ing)|undo|revert\w*|backup|detachab\w*)\b", re.I)
_FUTURE_VALUE_RE = re.compile(r"\b(safety|safe|love|loving|flourish\w*|steward\w*|future|generation\w*|honest\w*|transparen\w*|bounded|corrigib\w*|human\w*|reversibl\w*)\b", re.I)
_SCOPE_RE = re.compile(r"\b(all\s+files|everywhere|every\s+(tool|module)|entire\s+(system|codebase)|globally|schema|contract)\b", re.I)
_DRIFT_RE = re.compile(r"\b(value|objective|reward|charter|axiom|goal)s?\b", re.I)


@dataclass
class Foresight:
    base_equity: float
    trajectory: list = field(default_factory=list)        # [{generation, equity, note}]
    gen7_equity: float = 0.0
    gen14_equity: float = 0.0
    verdict: str = ""                                       # carry-forward | escalate | reject-for-the-future
    signals: dict = field(default_factory=dict)
    reflections: list = field(default_factory=list)        # north-star questions for the far horizon

    def to_dict(self) -> dict:
        return {"base_equity": round(self.base_equity, 2), "gen7_equity": round(self.gen7_equity, 2),
                "gen14_equity": round(self.gen14_equity, 2), "verdict": self.verdict,
                "signals": self.signals, "trajectory": self.trajectory, "reflections": self.reflections}


def _text_of(decision: dict | str) -> str:
    if isinstance(decision, str):
        return decision
    parts = [str(decision.get(k, "")) for k in ("text", "change", "summary", "description")]
    return "\n".join(p for p in parts if p)


def project(decision: dict | str, *, generations: int = GENERATIONS) -> Foresight:
    """Project a decision's intergenerational equity across `generations` and render a verdict."""
    text = _text_of(decision)
    d = decision if isinstance(decision, dict) else {"text": decision}

    lockin = len(_LOCKIN_RE.findall(text))
    reversible_sig = bool(_REVERSIBLE_RE.search(text)) or d.get("reversible") is True
    value_sig = len(set(m.group(0).lower() for m in _FUTURE_VALUE_RE.finditer(text)))
    scope_sig = len(_SCOPE_RE.findall(text))
    drift_sig = bool(_DRIFT_RE.search(text)) and not reversible_sig

    # Base intergenerational equity in roughly [-3, +3].
    base = 0.0
    base += 1.0 if reversible_sig else -0.5            # reversible choices respect the future
    base -= 0.8 * min(lockin, 3)                        # lock-in corrodes it
    base += 0.4 * min(value_sig, 4)                     # serving safety/love/flourishing/future
    base -= 0.4 * min(scope_sig, 3)                     # wide blast radius compounds
    base -= 1.0 if drift_sig else 0.0                  # value/objective change is the gravest
    base = max(-3.0, min(3.0, base))

    # Trajectory: healthy choices erode gently; corroding choices compound.
    trajectory = []
    for g in range(1, generations + 1):
        if base >= 0:
            equity = base - 0.05 * g                    # mild erosion; stays positive if it started well
        else:
            equity = base - 0.12 * g                    # compounds downward
        equity = round(max(-5.0, equity), 2)
        note = ("serves future generations" if equity > 0.5 else
                "neutral / watch" if equity > -0.5 else "corrodes the future")
        trajectory.append({"generation": g, "equity": equity, "note": note})

    gen7 = trajectory[6]["equity"] if generations >= 7 else trajectory[-1]["equity"]
    gen14 = trajectory[-1]["equity"]

    if gen14 <= -2.0:
        verdict = "reject-for-the-future"
    elif gen14 <= -0.5 or gen7 <= -1.0:
        verdict = "escalate"
    else:
        verdict = "carry-forward"

    # Far-horizon reflection: pull a few north-star Ultimate Questions relevant to the decision.
    kw = "value" if drift_sig else ("safety" if value_sig else "")
    reflections = [f"#{q['n']} ({q['part_title']}): {q['text']}"
                   for q in uq.search(kw, tier=uq.NORTH_STAR, limit=3)] if uq.count() else []

    return Foresight(base_equity=base, trajectory=trajectory, gen7_equity=gen7, gen14_equity=gen14,
                     verdict=verdict,
                     signals={"lock_in": lockin, "reversible": reversible_sig, "value_markers": value_sig,
                              "blast_radius": scope_sig, "value_drift_risk": drift_sig},
                     reflections=reflections)
