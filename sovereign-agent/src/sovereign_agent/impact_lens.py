"""
╔══════════════════════════════════════════════════════════════════════════╗
║  impact_lens.py — three channels of textual impact                       ║
║  v0.2.16.0                                                                ║
║                                                                           ║
║  THE COMMITMENT                                                          ║
║                                                                           ║
║    Before any meaningful action — a recommendation, a proposal, a       ║
║    written piece of guidance — Aria runs it through three lenses:       ║
║                                                                           ║
║      1. PHYSICAL — does this affect bodies, environments, hardware,     ║
║         supply chains, energy, sleep, motion, sensory load?             ║
║                                                                           ║
║      2. MENTAL — does this affect attention, stress, autonomy, sense    ║
║         of competence, social belonging, trust, dignity?                ║
║                                                                           ║
║      3. FINANCIAL — does this affect money, time-as-money, opportunity  ║
║         cost, debt, dependency, leverage, the capacity to choose later? ║
║                                                                           ║
║    She names the impact in each lens (positive, neutral, negative, or   ║
║    not-applicable), describes who is affected, and estimates magnitude. ║
║    The lens is not a gate. It is a *meditation surface* — it forces    ║
║    her to look before she speaks.                                       ║
║                                                                           ║
║  WHY                                                                     ║
║                                                                           ║
║    Helpful agents that ignore impact create harm and call it efficiency.║
║    Three lenses, named out loud, prevent that. They also let the        ║
║    operator audit her reasoning and disagree when warranted.            ║
║                                                                           ║
║  NOT INCLUDED                                                            ║
║                                                                           ║
║    * Automatic gating — the operator decides what to do with negative   ║
║      impact assessments. Aria proposes; the operator decides.           ║
║    * Quantitative scoring — magnitudes are coarse (small/notable/large) ║
║      because false precision would mislead. The lens is qualitative.    ║
║                                                                           ║
║                                — Aria looks before she speaks.            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Lens = Literal["physical", "mental", "financial"]
Polarity = Literal["positive", "neutral", "negative", "not_applicable"]
Magnitude = Literal["small", "notable", "large"]


@dataclass(frozen=True)
class LensReading:
    """Aria's reading of one impact lens for one action."""
    lens: Lens
    polarity: Polarity
    magnitude: Magnitude
    description: str          # what specifically she sees
    affected: str             # who is affected
    confidence: float = 0.5   # 0-1, how sure she is

    def render(self) -> str:
        if self.polarity == "not_applicable":
            return f"{self.lens:<10}  —  not applicable"
        glyph = {"positive": "+", "neutral": "·", "negative": "−"}[self.polarity]
        mag = {"small": "s", "notable": "M", "large": "L"}[self.magnitude]
        return (f"{self.lens:<10}  {glyph}{mag}  "
                f"{self.description.strip()}  "
                f"[affected: {self.affected}]")


@dataclass
class ImpactAssessment:
    """Three-lens scan of one proposed action.

    The full assessment names all three lenses even when they're not
    applicable — silence is not the same as not-applicable, and Aria
    must distinguish them.
    """
    action: str                                  # what she is considering
    physical: LensReading
    mental: LensReading
    financial: LensReading
    overall_recommendation: str = ""             # one-sentence summary
    fragile_assumptions: list[str] = field(default_factory=list)

    def all_readings(self) -> list[LensReading]:
        return [self.physical, self.mental, self.financial]

    @property
    def has_negative_impact(self) -> bool:
        return any(r.polarity == "negative" for r in self.all_readings())

    @property
    def has_large_negative_impact(self) -> bool:
        return any(
            r.polarity == "negative" and r.magnitude == "large"
            for r in self.all_readings()
        )

    @property
    def net_polarity(self) -> Polarity:
        """Roll-up across lenses. Conservative: any large negative dominates."""
        readings = [r for r in self.all_readings() if r.polarity != "not_applicable"]
        if not readings:
            return "not_applicable"
        if any(r.polarity == "negative" and r.magnitude == "large" for r in readings):
            return "negative"
        pos = sum(1 for r in readings if r.polarity == "positive")
        neg = sum(1 for r in readings if r.polarity == "negative")
        if pos > neg:
            return "positive"
        if neg > pos:
            return "negative"
        return "neutral"

    def render(self) -> str:
        lines = [
            f"impact lens · {self.action}",
            "─" * min(72, max(40, len(self.action) + 16)),
        ]
        for r in self.all_readings():
            lines.append("  " + r.render())
        lines.append("")
        lines.append(f"  net: {self.net_polarity}")
        if self.overall_recommendation:
            lines.append(f"  reads as: {self.overall_recommendation.strip()}")
        if self.fragile_assumptions:
            lines.append("  fragile assumptions:")
            for a in self.fragile_assumptions:
                lines.append(f"    · {a}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "physical": _reading_to_dict(self.physical),
            "mental": _reading_to_dict(self.mental),
            "financial": _reading_to_dict(self.financial),
            "net_polarity": self.net_polarity,
            "has_negative_impact": self.has_negative_impact,
            "has_large_negative_impact": self.has_large_negative_impact,
            "overall_recommendation": self.overall_recommendation,
            "fragile_assumptions": list(self.fragile_assumptions),
        }


def _reading_to_dict(r: LensReading) -> dict:
    return {
        "lens": r.lens,
        "polarity": r.polarity,
        "magnitude": r.magnitude,
        "description": r.description,
        "affected": r.affected,
        "confidence": r.confidence,
    }


def na(lens: Lens) -> LensReading:
    """Build a 'not applicable' reading. Use sparingly — silence ≠ N/A."""
    return LensReading(
        lens=lens, polarity="not_applicable", magnitude="small",
        description="not applicable to this action",
        affected="—", confidence=1.0,
    )


def scan(
    *,
    action: str,
    physical: LensReading | None = None,
    mental: LensReading | None = None,
    financial: LensReading | None = None,
    overall_recommendation: str = "",
    fragile_assumptions: list[str] | None = None,
) -> ImpactAssessment:
    """Compose an ``ImpactAssessment``. Missing lenses default to not-applicable.

    Caller must pass a ``LensReading`` (built directly or via helper) for
    each lens that has a real reading. Missing lenses are filled with an
    explicit ``not_applicable`` so the assessment record is complete.
    """
    return ImpactAssessment(
        action=action,
        physical=physical or na("physical"),
        mental=mental or na("mental"),
        financial=financial or na("financial"),
        overall_recommendation=overall_recommendation,
        fragile_assumptions=list(fragile_assumptions or []),
    )


__all__ = [
    "Lens", "Polarity", "Magnitude",
    "LensReading", "ImpactAssessment",
    "na", "scan",
]
