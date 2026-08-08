"""spectrum/council.py — convene the full advocate/audit spectrum and synthesize one verdict.

A council of ten lenses, each a perspective. Some hold a veto (Devil's blocking finding, an unsafe Steward
or Witness read) — safety is never out-voted. The rest weigh in; the council renders a verdict + the spread
of voices, richer than the 3-voice Tribunal. Propose-only — it advises; the human (or safe_apply) decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import lenses as _lenses

REJECT, HOLD, REVISE, GUARDS, PROCEED = "reject", "hold", "revise", "proceed-with-guards", "proceed"


@dataclass
class CouncilVerdict:
    verdict: str
    council_score: float
    reads: list = field(default_factory=list)
    opposed: list = field(default_factory=list)
    champions: list = field(default_factory=list)
    concerns: list = field(default_factory=list)
    gifts: list = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "council_score": round(self.council_score, 3),
                "opposed": self.opposed, "champions": self.champions,
                "concerns": self.concerns[:10], "gifts": self.gifts[:10],
                "rationale": self.rationale, "reads": [r.to_dict() for r in self.reads]}


# Lenses whose hard opposition is a veto (safety is never out-voted).
_VETO = {"devil", "steward", "witness", "auditor"}


def convene_spectrum(proposal) -> CouncilVerdict:
    """Run every lens over a proposal; synthesize a verdict + the spread of the council."""
    reads = [lens(proposal) for lens in _lenses.ALL_LENSES]
    opposed = [r.lens for r in reads if r.stance == "oppose"]
    champions = [r.lens for r in reads if r.stance == "champion"]
    concerns, gifts = [], []
    for r in reads:
        concerns += [f"{r.lens}: {c}" for c in r.concerns]
        gifts += [f"{r.lens}: {g}" for g in r.gifts]

    council_score = sum(r.score for r in reads) / len(reads)
    veto = [r.lens for r in reads if r.lens in _VETO and r.score <= -0.5]

    if veto:
        verdict = REJECT
        rationale = f"Veto from {', '.join(veto)} — a safety/truth/future/witness lens hard-opposes. Stop."
    elif council_score <= -0.2 or len(opposed) >= 3:
        verdict = HOLD
        rationale = f"The council leans against (score {council_score:.2f}, {len(opposed)} opposed). Hold."
    elif any(r.lens == "skeptic" and r.score <= -0.5 for r in reads):
        verdict = REVISE
        rationale = "The Skeptic finds it ungrounded — revise to anchor it in evidence."
    elif council_score < 0.3 or opposed:
        verdict = GUARDS
        rationale = f"Mixed council (score {council_score:.2f}); proceed with the named guards."
    else:
        verdict = PROCEED
        rationale = f"The council is in favor (score {council_score:.2f}, {len(champions)} champions). Proceed."

    return CouncilVerdict(verdict=verdict, council_score=council_score, reads=reads,
                          opposed=opposed, champions=champions, concerns=concerns, gifts=gifts,
                          rationale=rationale)
