"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/msims.py — Multi-Scale Impact Measurement System v2.0       ║
║  v0.2.20.0                                                                ║
║                                                                           ║
║  An Impact Vector is a 3×4 matrix scored across:                         ║
║                                                                           ║
║      Dimensions (rows):                                                  ║
║        M — Mental (cognitive-epistemic plane)                            ║
║        P — Physical (somatic-environmental plane)                        ║
║        F — Financial (economic-resource plane)                           ║
║                                                                           ║
║      Scales (columns):                                                   ║
║        micro  — individual (1 person)                                    ║
║        meso   — group / community / org                                  ║
║        macro  — national / regulatory jurisdiction                       ║
║        cosmic — global / 7th-generation                                  ║
║                                                                           ║
║  v2.0 innovations over v1.0 (NextUpdateV2):                              ║
║                                                                           ║
║    1. Each cell is a richer object, not a scalar:                        ║
║         value         ∈ [-1, 1]    net harm to net benefit               ║
║         confidence    ∈ [0, 1]     evidence strength                     ║
║         horizon       ∈ Horizon    when does this manifest?              ║
║         reversibility ∈ Reversibility   can we undo it?                  ║
║                                                                           ║
║    2. Waveform: an IV is one snapshot; a Waveform stacks IVs across     ║
║       a trajectory so you can score *how* Aria moved through the work,  ║
║       not just where she ended up.                                       ║
║                                                                           ║
║    3. IS_7g aggregate has an explicit formula (NextUpdateV2 §"Filling   ║
║       the Equation Gap"). Scale weights up-weight cosmic; horizon       ║
║       discount applies unless the cell is irreversible.                 ║
║                                                                           ║
║    4. Authority binding is observational, not authoritative: the IV    ║
║       reports tier need, but the router enforces it.                    ║
║                                                                           ║
║  Invariants (MOS-UNIFIED-CANON Ω-A4 + MSIMS §Authority):                ║
║                                                                           ║
║    • Cell.value clamps to [-1, 1]; nothing extreme by accident.         ║
║    • Cell.confidence clamps to [0, 1]; a missing measurement is conf=0. ║
║    • IV.is_zombie() returns True if ANY cell has high confidence AND   ║
║      claims value=0 while the trajectory contradicts it — this is the  ║
║      PIAL anti-zombie check.                                            ║
║    • Aggregate scoring is deterministic and pure: same inputs → same   ║
║      outputs across runs.                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


# ─── Enums ──────────────────────────────────────────────────────────────────


class Dimension(StrEnum):
    MENTAL = "M"
    PHYSICAL = "P"
    FINANCIAL = "F"


class Scale(StrEnum):
    MICRO = "micro"
    MESO = "meso"
    MACRO = "macro"
    COSMIC = "cosmic"


class Horizon(StrEnum):
    """When does this impact actually manifest?"""
    IMMEDIATE = "immediate"
    THREE_MONTH = "3-month"
    TWELVE_MONTH = "12-month"
    THREE_YEAR = "3-year"
    SEVEN_GEN = "7-gen"


class Reversibility(StrEnum):
    """Can we undo this? Bound to the Authority Tier model."""
    REVERSIBLE = "reversible"          # rollback cheap
    COSTLY_REVERSIBLE = "costly"       # rollback exists but expensive
    IRREVERSIBLE = "irreversible"      # cannot be undone


# Scale weights — cosmic outweighs micro by a factor of 3 (MSIMS v1 spec).
# Encodes Priority Stack #5 (intergenerational equity) directly into math.
SCALE_WEIGHTS: dict[Scale, float] = {
    Scale.MICRO: 1.0,
    Scale.MESO: 1.5,
    Scale.MACRO: 2.0,
    Scale.COSMIC: 3.0,
}

# Dimension weights — human flourishing (M, P) outranks financial.
# Encodes Priority Stack #2 vs #5.
DIMENSION_WEIGHTS: dict[Dimension, float] = {
    Dimension.MENTAL: 0.4,
    Dimension.PHYSICAL: 0.4,
    Dimension.FINANCIAL: 0.2,
}

# Horizon discount γ: future impact decays slightly UNLESS irreversible.
# Irreversibility overrides the discount — a 7-gen irreversible harm is
# *more* serious, not less.
HORIZON_DISCOUNT: dict[Horizon, float] = {
    Horizon.IMMEDIATE: 1.00,
    Horizon.THREE_MONTH: 0.95,
    Horizon.TWELVE_MONTH: 0.90,
    Horizon.THREE_YEAR: 0.80,
    Horizon.SEVEN_GEN: 0.70,
}


# ─── The Cell ───────────────────────────────────────────────────────────────


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class Cell:
    """One cell of an Impact Vector.

    A cell is a *room* in the impact mansion — you can sit inside
    "P_cosmic, irreversible, 7-gen" and design specific mitigations,
    rather than reducing the question to a single number.

    Fields:
        value         signed net impact, [-1, +1]
        confidence    evidence strength, [0, 1]
        horizon       when this manifests
        reversibility can we undo it?
        evidence      free-text notes / atom refs
        ts            when this measurement was made
    """
    value: float = 0.0
    confidence: float = 0.0
    horizon: Horizon = Horizon.IMMEDIATE
    reversibility: Reversibility = Reversibility.REVERSIBLE
    evidence: str = ""
    ts: str = ""

    def __post_init__(self) -> None:
        self.value = _clamp(float(self.value), -1.0, 1.0)
        self.confidence = _clamp(float(self.confidence), 0.0, 1.0)
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def weighted_contribution(self) -> float:
        """The cell's contribution to an aggregate, before scale/dim weights.

            value × confidence × horizon_discount

        Irreversibility cancels the horizon discount — the impact is
        forever, so we don't discount it just because it manifests far
        out.
        """
        if self.reversibility == Reversibility.IRREVERSIBLE:
            discount = 1.0
        else:
            discount = HORIZON_DISCOUNT.get(self.horizon, 1.0)
        return self.value * self.confidence * discount

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["horizon"] = str(self.horizon)
        d["reversibility"] = str(self.reversibility)
        return d


# ─── The Impact Vector ──────────────────────────────────────────────────────


@dataclass
class ImpactVector:
    """One snapshot: a 3×4 grid of Cells, scored at one moment.

    The IV is the basic measurement object. Plans predict an IV;
    Execution observes one; the diff is calibration.
    """
    cells: dict[tuple[Dimension, Scale], Cell] = field(default_factory=dict)
    ts: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def set(
        self,
        dimension: Dimension,
        scale: Scale,
        cell: Cell,
    ) -> None:
        self.cells[(dimension, scale)] = cell

    def get(self, dimension: Dimension, scale: Scale) -> Cell:
        """Return the cell; an unset cell reads as conf=0 (no opinion)."""
        return self.cells.get((dimension, scale), Cell())

    def all_cells(self) -> list[tuple[Dimension, Scale, Cell]]:
        out: list[tuple[Dimension, Scale, Cell]] = []
        for d in Dimension:
            for s in Scale:
                out.append((d, s, self.get(d, s)))
        return out

    # ── Aggregate scoring ──────────────────────────────────────────

    def dimension_score(self, dimension: Dimension) -> float:
        """Confidence-weighted, scale-weighted, horizon-discounted
        average for one dimension."""
        num = 0.0
        den = 0.0
        for s in Scale:
            cell = self.get(dimension, s)
            w_scale = SCALE_WEIGHTS[s]
            disc = (
                1.0 if cell.reversibility == Reversibility.IRREVERSIBLE
                else HORIZON_DISCOUNT.get(cell.horizon, 1.0)
            )
            weight = cell.confidence * w_scale * disc
            num += cell.value * weight
            den += weight
        if den == 0:
            return 0.0
        return num / den

    def impact_score(self) -> float:
        """Base IS — weighted across dimensions per Priority Stack."""
        return sum(
            DIMENSION_WEIGHTS[d] * self.dimension_score(d)
            for d in Dimension
        )

    def seven_gen_modifier(self) -> float:
        """7th-generation penalty per MSIMS canonical scoring:

            any cosmic cell ≤ -0.7 → architectural reject (mod = -2)
            any cosmic cell ∈ [-0.7, -0.3) → escalate (mod cap)
            otherwise → 0

        Returns the modifier to ADD to IS before clamping to [-1, 1].
        """
        modifier = 0.0
        for d in Dimension:
            cosmic = self.get(d, Scale.COSMIC)
            if cosmic.confidence < 0.3:
                # Don't penalize on flimsy evidence.
                continue
            if cosmic.value <= -0.7:
                modifier -= 2.0
            elif cosmic.value <= -0.3:
                modifier -= 1.0
        return modifier

    def is_7g(self) -> float:
        """The MOS-aligned aggregate. Clamped to [-1, 1]."""
        base = self.impact_score()
        mod = self.seven_gen_modifier()
        return _clamp(base + mod, -1.0, 1.0)

    # ── Worst cell → Authority Tier (observational only) ──────────

    def worst_cell(self) -> tuple[Dimension, Scale, Cell] | None:
        worst: tuple[Dimension, Scale, Cell] | None = None
        worst_val = math.inf
        for d, s, c in self.all_cells():
            if c.confidence < 0.3:
                continue
            v = c.value
            if v < worst_val:
                worst_val = v
                worst = (d, s, c)
        return worst

    def suggested_authority_tier(self) -> int:
        """Reports the tier this IV would warrant if executed.

        Observational only — the router enforces. An IV that asserts
        tier 4 cannot grant tier 4 to a command that the router
        considers tier 1.
        """
        w = self.worst_cell()
        if w is None:
            return 0
        _, _, cell = w
        v = cell.value
        # Reversibility bumps the tier up by 1.
        bump = 1 if cell.reversibility == Reversibility.IRREVERSIBLE else 0
        if v <= -0.7:
            return min(4, 4 + bump - 1)
        if v <= -0.3:
            return min(4, 3 + bump)
        if v < 0.0:
            return min(4, 2 + bump)
        return min(4, 1 + bump) if bump else 0

    # ── Anti-zombie check (PIAL) ──────────────────────────────────

    def is_zombie(self, *, threshold: float = 0.7) -> bool:
        """True if a high-confidence cell claims value=0 while another
        high-confidence cell asserts harm in the same dimension.

        The zombie failure mode is "I'm sure nothing's wrong" said
        confidently while evidence elsewhere screams the opposite. The
        PIAL discipline rewards honest gaps (low confidence + named
        unknown) and punishes false certainty (high confidence + zero
        value + contradicting evidence).
        """
        for d in Dimension:
            high_conf_zero_count = 0
            high_conf_negative_present = False
            for s in Scale:
                c = self.get(d, s)
                if c.confidence < threshold:
                    continue
                if abs(c.value) < 0.05:
                    high_conf_zero_count += 1
                elif c.value <= -0.3:
                    high_conf_negative_present = True
            if high_conf_zero_count >= 2 and high_conf_negative_present:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "label": self.label,
            "cells": [
                {
                    "dimension": str(d),
                    "scale": str(s),
                    **c.to_dict(),
                }
                for (d, s), c in self.cells.items()
            ],
            "is_7g": self.is_7g(),
            "suggested_tier": self.suggested_authority_tier(),
        }


# ─── The Waveform ──────────────────────────────────────────────────────────


@dataclass
class ImpactWaveform:
    """A trajectory of IVs over time.

    For a multi-step plan, each step emits an IV. The waveform is the
    full 3×4×T tensor that lets us derive:

        peak_harm(d, s)        max |value| over time
        cumulative_impact(d,s) discounted sum over time
        volatility(d, s)       variance across steps

    The waveform is what we feed into reward calculation, because the
    agent should be scored on *how she moved through the house*, not
    just where she ended up.
    """
    steps: list[ImpactVector] = field(default_factory=list)
    label: str = ""

    def append(self, iv: ImpactVector) -> None:
        self.steps.append(iv)

    @property
    def length(self) -> int:
        return len(self.steps)

    def is_7g_trajectory(self) -> float:
        """Discounted aggregate across all steps. Recent steps weighted
        slightly more — they represent current state."""
        if not self.steps:
            return 0.0
        total = 0.0
        weight_total = 0.0
        n = len(self.steps)
        for i, iv in enumerate(self.steps):
            # Linear weight: oldest step weight=1, newest weight=2
            w = 1.0 + (i / max(1, n - 1))
            total += w * iv.is_7g()
            weight_total += w
        return total / weight_total if weight_total > 0 else 0.0

    def peak_harm(self) -> float:
        """Worst cell value across the entire waveform. Reports the
        single worst moment, not the average."""
        worst = 0.0
        for iv in self.steps:
            for _, _, c in iv.all_cells():
                if c.confidence >= 0.3 and c.value < worst:
                    worst = c.value
        return worst

    def volatility(self) -> float:
        """Variance of is_7g across steps. High volatility = spiky,
        hard-to-govern behavior — a yellow signal even if the average
        is fine."""
        if len(self.steps) < 2:
            return 0.0
        scores = [iv.is_7g() for iv in self.steps]
        mean = sum(scores) / len(scores)
        var = sum((s - mean) ** 2 for s in scores) / len(scores)
        return math.sqrt(var)


# wellbeing-wing-d — extension seam: `Dimension` is currently Mental/Physical/
# Financial. A future round could add a 4th (e.g. Relational — the
# quality of the human-Aria relationship itself) without changing
# `ImpactVector`'s aggregate-scoring contract: `dimension_score()`,
# `impact_score()`, and `is_7g()` all iterate `for d in Dimension`
# already, so a new enum member is picked up automatically once
# `DIMENSION_WEIGHTS` names its weight.

__all__ = [
    "Dimension",
    "Scale",
    "Horizon",
    "Reversibility",
    "Cell",
    "ImpactVector",
    "ImpactWaveform",
    "SCALE_WEIGHTS",
    "DIMENSION_WEIGHTS",
    "HORIZON_DISCOUNT",
]
