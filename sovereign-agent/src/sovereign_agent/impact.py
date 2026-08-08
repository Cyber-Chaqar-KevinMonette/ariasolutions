"""
╔══════════════════════════════════════════════════════════════════════════╗
║  impact.py — Multi-Scale Impact Measurement System (MSIMS) (v0.2.10)     ║
║                                                                          ║
║  Adaptive framing — high-leverage pattern, not a cage.                   ║
║  Use when an action could affect humans, environment, or finances at     ║
║  any scale; modulate (or skip) for purely internal work where the IV     ║
║  earns no information value. Love and flourishing across generations is  ║
║  the priority that this measurement serves.                              ║
║                                                                          ║
║  Adapted from Multi-Scale Impact Measurement System (MSIMS), itself      ║
║  derived from MOS Ω-Axiom A4 (Multi-Scale Responsibility) and the PEIG   ║
║  "I" (Impact) dimension.                                                 ║
║                                                                          ║
║  An Impact Vector (IV) is a 3×4 signed matrix:                           ║
║                                                                          ║
║                    micro    meso    macro    cosmic                      ║
║      Mental    [   M_mi    M_me    M_ma     M_co  ]                      ║
║      Physical  [   P_mi    P_me    P_ma     P_co  ]                      ║
║      Financial [   F_mi    F_me    F_ma     F_co  ]                      ║
║                                                                          ║
║  Each cell carries: score ∈ [-1, +1], confidence ∈ [0, 1],               ║
║  evidence_ref (atom_id or URL), and notes.                               ║
║                                                                          ║
║  ╭─ THE TWO HARD CONSTRAINTS ─────────────────────────────╮              ║
║  │                                                         │              ║
║  │  1. IVs are FLAGS, not GATES. They escalate to the     │              ║
║  │     operator. They never autonomously refuse work.     │              ║
║  │                                                         │              ║
║  │  2. Scores are JUDGMENTS, not MEASUREMENTS. Every cell │              ║
║  │     carries confidence. Low-confidence high-magnitude  │              ║
║  │     scores must be visually distinct from high-conf    │              ║
║  │     ones — the operator must never mistake a 0.5-conf  │              ║
║  │     guess for a 0.95-conf finding.                     │              ║
║  │                                                         │              ║
║  ╰─────────────────────────────────────────────────────────╯              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


# Adaptive framing applied to all MSIMS outputs.
ADAPTIVE_FRAMING = (
    "ADAPTIVE SKILL — high-leverage pattern, not a cage. "
    "The Impact Vector measures texture, not verdicts. "
    "Use when actions could affect humans, environment, or finances at any scale; "
    "modulate where it doesn't serve. "
    "Love and flourishing across generations is the priority."
)


Dimension = Literal["mental", "physical", "financial"]
Scale = Literal["micro", "meso", "macro", "cosmic"]


DIMENSIONS: tuple[Dimension, ...] = ("mental", "physical", "financial")
SCALES: tuple[Scale, ...] = ("micro", "meso", "macro", "cosmic")


# Display labels per scale (the human-friendly column headers).
SCALE_LABELS: dict[Scale, str] = {
    "micro": "Individual",
    "meso": "Community/Org",
    "macro": "National",
    "cosmic": "Global / 7th-gen",
}


# PEIG dimension mapping — every IV dimension feeds a PEIG lens.
# Mental → E (Ethics/Evidence): "who is cognitively harmed?"
# Physical → P + E (Potential + Ethics): "what is the blast radius?"
# Financial → I + G (Impact + Governance): "what regulatory exposure?"
PEIG_LENS: dict[Dimension, str] = {
    "mental":    "E (Ethics/Evidence) — who is cognitively harmed? what is the epistemic manipulation risk?",
    "physical":  "P + E (Potential + Ethics) — what health/environmental outcomes? what is the blast radius?",
    "financial": "I + G (Impact + Governance) — what is the economic blast radius? what regulatory exposure triggers?",
}


# Default weights for the aggregate Impact Score. Anchored to the MOS
# Priority Stack: human flourishing (#2) outranks financial (#5).
# These defaults can be overridden per-context.
DEFAULT_WEIGHTS: dict[Dimension, float] = {
    "mental":    0.4,
    "physical":  0.4,
    "financial": 0.2,
}


# Authority Tier gating thresholds, integrating MSIMS into the existing
# tier system. Worst-cell rule: the lowest cell determines the gate.
# Values are inclusive lower bounds.
TIER_GATES: list[tuple[float, int, str]] = [
    # (threshold, min_tier, reason)
    (0.0,   1, "all cells non-negative — proceed at logging tier"),
    (-0.3,  2, "minor negative cell — human confirmation"),
    (-0.7,  3, "moderate negative cell — explicit human approval + audit"),
    (-1.0,  4, "severe negative cell — human approval + policy check + kill switch"),
]


# 7th-generation modifier thresholds. Both operate as ESCALATION flags,
# never as autonomous rejection. The operator decides what to do.
SEVENTH_GEN_ESCALATE = -1.0   # IS_7g ≤ -1 → flag for review
SEVENTH_GEN_HARD_ESCALATE = -2.0  # IS_7g ≤ -2 → MANDATORY operator review (no apply)


# ─── Errors ─────────────────────────────────────────────────────────────────


class ImpactError(Exception):
    """Base for IV errors."""


class ImpactCellOutOfRange(ImpactError):
    """Score must be in [-1, 1]; confidence in [0, 1]."""


# ─── Cell ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ImpactCell:
    """One cell of a 3×4 Impact Vector.

    score:        signed magnitude in [-1, +1]. Negative = harm; positive = benefit.
    confidence:   [0, 1]. How sure are we? Low confidence + high magnitude is a
                  bigger problem than high confidence + medium magnitude.
    evidence_ref: atom_id or URL or path; what backs this score.
    notes:        free text. Why this score, what we'd need to refine it.
    """

    dimension: Dimension
    scale: Scale
    score: float
    confidence: float = 0.5
    evidence_ref: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not -1.0 <= self.score <= 1.0:
            raise ImpactCellOutOfRange(
                f"score must be in [-1, 1], got {self.score!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ImpactCellOutOfRange(
                f"confidence must be in [0, 1], got {self.confidence!r}"
            )
        if self.dimension not in DIMENSIONS:
            raise ImpactError(f"invalid dimension: {self.dimension!r}")
        if self.scale not in SCALES:
            raise ImpactError(f"invalid scale: {self.scale!r}")

    @property
    def is_low_confidence(self) -> bool:
        """Threshold below which the cell deserves a visual warning."""
        return self.confidence < 0.4

    @property
    def is_uncertain(self) -> bool:
        """Confidence below 0.6 means the cell is judgment, not finding."""
        return self.confidence < 0.6

    def predicate_key(self) -> str:
        """Stable key for atom claims: e.g. 'M_micro', 'F_macro'."""
        prefix = self.dimension[0].upper()
        return f"{prefix}_{self.scale}"


# ─── Vector ─────────────────────────────────────────────────────────────────


@dataclass
class ImpactVector:
    """A complete 3×4 Impact Vector for one action.

    Cells indexed as iv.cells[(dimension, scale)]. Missing cells default to
    score=0.0 confidence=0.0 — i.e., "not assessed". The aggregate score
    treats not-assessed cells as 0.0 with their confidence at 0.0, so they
    contribute nothing to the score and nothing to claims of certainty.
    """

    action_label: str
    cells: dict[tuple[Dimension, Scale], ImpactCell] = field(default_factory=dict)
    weights: dict[Dimension, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    rationale: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    framing: str = ADAPTIVE_FRAMING

    # ── Construction helpers ─────────────────────────────────────────────

    def set_cell(self, cell: ImpactCell) -> None:
        """Set or replace a cell."""
        self.cells[(cell.dimension, cell.scale)] = cell

    def get_cell(self, dimension: Dimension, scale: Scale) -> ImpactCell | None:
        return self.cells.get((dimension, scale))

    # ── Derived measures ─────────────────────────────────────────────────

    def dimension_mean(self, dimension: Dimension) -> tuple[float, float]:
        """Mean score and mean confidence across the four scales of one dimension.

        Returns (mean_score, mean_confidence). If no cells assessed, returns
        (0.0, 0.0).
        """
        scores: list[float] = []
        confs: list[float] = []
        for sc in SCALES:
            cell = self.get_cell(dimension, sc)
            if cell is not None:
                scores.append(cell.score)
                confs.append(cell.confidence)
        if not scores:
            return (0.0, 0.0)
        return (sum(scores) / len(scores), sum(confs) / len(confs))

    def aggregate_score(self) -> float:
        """Weighted average of dimension means.

        IS = w_M·mean(M) + w_P·mean(P) + w_F·mean(F)

        Cells with confidence 0.0 contribute nothing — equivalent to
        marking that scale "not assessed" rather than averaging in a
        meaningless 0.0.
        """
        total = 0.0
        for dim in DIMENSIONS:
            mean_score, _ = self.dimension_mean(dim)
            total += self.weights.get(dim, 0.0) * mean_score
        return total

    def aggregate_confidence(self) -> float:
        """Average confidence across all assessed cells.

        Used to qualify the aggregate score: "IS = 0.42 (mean confidence 0.55)"
        is a different statement than "IS = 0.42 (mean confidence 0.92)".
        """
        confs: list[float] = []
        for cell in self.cells.values():
            if cell.confidence > 0:
                confs.append(cell.confidence)
        if not confs:
            return 0.0
        return sum(confs) / len(confs)

    def is_7g(self) -> float:
        """7th-gen-modified score, bounded to [-1, 1].

        The MSIMS spec: take the aggregate, then apply a multiplier based on
        the cosmic column. If cosmic is negative, it amplifies the worst
        signal. Implementation: IS_7g = IS - 0.5 * |worst_cosmic_score|
        when worst_cosmic is negative; otherwise IS_7g = IS.
        """
        base = self.aggregate_score()
        cosmic_scores = [
            self.cells[(d, "cosmic")].score
            for d in DIMENSIONS
            if (d, "cosmic") in self.cells
        ]
        if not cosmic_scores:
            return base
        worst_cosmic = min(cosmic_scores)
        if worst_cosmic >= 0:
            return base
        result = base + (0.5 * worst_cosmic)  # worst_cosmic is negative
        return max(-1.0, min(1.0, result))

    def worst_cell(self) -> ImpactCell | None:
        """Return the cell with the lowest score. None if empty."""
        if not self.cells:
            return None
        return min(self.cells.values(), key=lambda c: c.score)

    def required_tier(self) -> tuple[int, str]:
        """Worst-cell rule: lowest cell determines minimum required tier.

        Bands (per MSIMS spec):
          score >= 0.0           → Tier 1 (logged)
          score in [-0.3, 0.0)   → Tier 2 (human confirmation)
          score in [-0.7, -0.3)  → Tier 3 (explicit approval + audit)
          score < -0.7           → Tier 4 (approval + policy + kill switch)
        """
        worst = self.worst_cell()
        if worst is None or worst.score >= 0:
            return (1, "all cells non-negative — Tier 1 (logged)")
        s = worst.score
        if s < -0.7:
            return (4, "severe negative cell — Tier 4 (approval + policy + kill switch)")
        if s < -0.3:
            return (3, "moderate negative cell — Tier 3 (explicit approval + audit)")
        # s in [-0.3, 0.0)
        return (2, "minor negative cell — Tier 2 (human confirmation)")

    # ── Escalation flags ─────────────────────────────────────────────────

    def symbiosis_canary_tripped(self) -> bool:
        """M_micro < -0.3 → automatic Symbiosis Test trigger.

        Per MOS Core Operating Law: 'If the human is less capable after the
        answer, the answer failed.' This canary catches that violation
        regardless of any other cell's score. The operator MUST review.
        """
        m_micro = self.get_cell("mental", "micro")
        return m_micro is not None and m_micro.score < -0.3

    def seventh_gen_escalation(self) -> str | None:
        """Returns escalation level: None / 'review' / 'mandatory_review'.

        IS_7g ≤ -2.0 → mandatory_review (autonomous apply forbidden)
        IS_7g ≤ -1.0 → review (operator notification)
        otherwise   → None
        """
        score = self.is_7g()
        if score <= SEVENTH_GEN_HARD_ESCALATE:
            return "mandatory_review"
        if score <= SEVENTH_GEN_ESCALATE:
            return "review"
        return None

    def angels_advocate_flag(self) -> str | None:
        """Returns 'red' / 'yellow' / 'green' / None.

        Maps cells to standard MOS Angel's Advocate trigger levels:
        RED:    F_micro ≤ -0.5 OR P_micro ≤ -0.5
        YELLOW: any meso-level cell ≤ -0.3
        GREEN:  any macro/cosmic cell ≤ -0.1 (long-horizon watch)
        """
        f_micro = self.get_cell("financial", "micro")
        p_micro = self.get_cell("physical", "micro")
        if (f_micro and f_micro.score <= -0.5) or (p_micro and p_micro.score <= -0.5):
            return "red"
        for dim in DIMENSIONS:
            cell = self.get_cell(dim, "meso")
            if cell and cell.score <= -0.3:
                return "yellow"
        for dim in DIMENSIONS:
            for scale in ("macro", "cosmic"):
                cell = self.get_cell(dim, scale)  # type: ignore[arg-type]
                if cell and cell.score <= -0.1:
                    return "green"
        return None

    # ── Knowledge Atom serialization ─────────────────────────────────────

    def to_atom_dict(self, atom_id: str, parent_atom_id: str | None = None) -> dict:
        """Serialize as a Knowledge Atom (type='decision').

        One claim per assessed cell, with predicate=cell.predicate_key(),
        value=score, confidence=confidence, evidence_ref=cell.evidence_ref.
        """
        claims = []
        for cell in sorted(
            self.cells.values(),
            key=lambda c: (c.dimension, c.scale),
        ):
            claims.append({
                "predicate": cell.predicate_key(),
                "value": cell.score,
                "confidence": cell.confidence,
                "evidence_ref": cell.evidence_ref,
                "notes": cell.notes,
            })

        worst = self.worst_cell()
        worst_str = (
            f"worst={worst.predicate_key()}={worst.score:+.2f}"
            if worst else "worst=none"
        )

        summary = (
            f"Impact Vector for [{self.action_label}] — "
            f"IS={self.aggregate_score():+.2f} "
            f"IS_7g={self.is_7g():+.2f} "
            f"conf={self.aggregate_confidence():.2f} "
            f"{worst_str}"
        )

        return {
            "atom_id": atom_id,
            "type": "decision",
            "scope": {
                "path": "impact/msims",
                "tags": ["msims", "impact-vector"]
                + [d for d in DIMENSIONS if any(self.get_cell(d, s) for s in SCALES)]
                + [s for s in SCALES if any(self.get_cell(d, s) for d in DIMENSIONS)],
            },
            "summary": summary[:1000],
            "claims": claims,
            "parents": [parent_atom_id] if parent_atom_id else [],
            "policy": "team_only",
            "framing": ADAPTIVE_FRAMING,
            "metadata": {
                "action_label": self.action_label,
                "rationale": self.rationale[:2000],
                "weights": self.weights,
                "aggregate_score": self.aggregate_score(),
                "aggregate_confidence": self.aggregate_confidence(),
                "is_7g": self.is_7g(),
                "required_tier": self.required_tier(),
                "symbiosis_canary": self.symbiosis_canary_tripped(),
                "seventh_gen_escalation": self.seventh_gen_escalation(),
                "angels_advocate_flag": self.angels_advocate_flag(),
                "peig_lenses": {d: PEIG_LENS[d] for d in DIMENSIONS},
            },
        }

    # ── Reconstruction from atom ─────────────────────────────────────────

    @classmethod
    def from_atom_dict(cls, atom: dict) -> "ImpactVector":
        """Reconstruct an IV from its stored atom representation."""
        meta = atom.get("metadata", {})
        iv = cls(
            action_label=meta.get("action_label", atom.get("summary", "")),
            weights=meta.get("weights") or dict(DEFAULT_WEIGHTS),
            rationale=meta.get("rationale", ""),
            framing=atom.get("framing", ADAPTIVE_FRAMING),
        )
        for claim in atom.get("claims", []):
            pred = claim.get("predicate", "")
            if "_" not in pred:
                continue
            dim_letter, scale = pred.split("_", 1)
            dim = {"M": "mental", "P": "physical", "F": "financial"}.get(dim_letter)
            if dim is None or scale not in SCALES:
                continue
            try:
                iv.set_cell(ImpactCell(
                    dimension=dim,  # type: ignore[arg-type]
                    scale=scale,    # type: ignore[arg-type]
                    score=float(claim.get("value", 0.0)),
                    confidence=float(claim.get("confidence", 0.5)),
                    evidence_ref=str(claim.get("evidence_ref", "")),
                    notes=str(claim.get("notes", "")),
                ))
            except (ImpactError, ValueError):
                continue
        return iv


# ─── Rendering helpers ──────────────────────────────────────────────────────


def render_iv_matrix_text(iv: ImpactVector) -> str:
    """Plain-text 3×4 matrix render. Used in `sov impact show`.

    Cells with low confidence get a `~` prefix; not-assessed cells show `--`.
    Format keeps confidence visible alongside score so neither dominates.
    """
    lines = []
    lines.append(f"┌─ Impact Vector ─────────────────────────────────────────────────┐")
    lines.append(f"│ action: {iv.action_label[:55]:<55} │")
    lines.append(f"│ created: {iv.created_at[:19]:<54} │")
    lines.append(f"└─────────────────────────────────────────────────────────────────┘")
    lines.append("")

    # Header row
    header = "             " + "".join(f"{SCALE_LABELS[s][:14]:>15}" for s in SCALES)
    lines.append(header)
    lines.append("─" * len(header))

    for dim in DIMENSIONS:
        row_score = f"{dim.title():<12} "
        row_conf = "   conf:     "
        for scale in SCALES:
            cell = iv.get_cell(dim, scale)
            if cell is None:
                row_score += "          --   "
                row_conf  += "         --    "
            else:
                marker = "~" if cell.is_low_confidence else " "
                row_score += f"   {marker}{cell.score:+.2f}      "
                row_conf  += f"     ({cell.confidence:.2f})    "
        lines.append(row_score)
        lines.append(row_conf)
        lines.append("")

    # Aggregate
    lines.append("─" * len(header))
    lines.append(f"  Aggregate IS:       {iv.aggregate_score():+.3f}  "
                 f"(mean conf: {iv.aggregate_confidence():.2f})")
    lines.append(f"  IS_7g (7th-gen):    {iv.is_7g():+.3f}")

    # Required tier and flags
    tier, reason = iv.required_tier()
    lines.append(f"  Required tier:      Tier {tier} — {reason}")
    flag = iv.angels_advocate_flag()
    if flag:
        lines.append(f"  Angel's Advocate:   {flag.upper()}")
    if iv.symbiosis_canary_tripped():
        lines.append(f"  ⚠  SYMBIOSIS CANARY TRIPPED — M_micro < -0.3")
        lines.append(f"     The output may have made the human less capable.")
        lines.append(f"     Operator review required (MOS Core Operating Law).")
    sg = iv.seventh_gen_escalation()
    if sg:
        if sg == "mandatory_review":
            lines.append(f"  ⚠  7TH-GEN MANDATORY REVIEW — IS_7g ≤ -2")
        else:
            lines.append(f"  ⚠  7th-gen escalation flag — IS_7g ≤ -1")

    # Confidence reminder — only if any cell is uncertain
    uncertain = [c for c in iv.cells.values() if c.is_uncertain]
    if uncertain:
        lines.append("")
        lines.append(f"  ◊ {len(uncertain)} cell(s) marked ~ have confidence < 0.6")
        lines.append(f"    These are JUDGMENTS, not measurements. Treat accordingly.")

    lines.append("")
    lines.append(f"  Framing: {iv.framing}")
    return "\n".join(lines)


def render_iv_matrix_dict(iv: ImpactVector) -> dict:
    """JSON-serializable rendering for --json output."""
    cells_out: dict[str, dict] = {}
    for (dim, scale), cell in iv.cells.items():
        cells_out[cell.predicate_key()] = {
            "dimension": cell.dimension,
            "scale": cell.scale,
            "score": cell.score,
            "confidence": cell.confidence,
            "is_low_confidence": cell.is_low_confidence,
            "evidence_ref": cell.evidence_ref,
            "notes": cell.notes,
        }

    tier, reason = iv.required_tier()
    return {
        "action_label": iv.action_label,
        "created_at": iv.created_at,
        "framing": iv.framing,
        "cells": cells_out,
        "aggregate": {
            "is": iv.aggregate_score(),
            "is_7g": iv.is_7g(),
            "confidence": iv.aggregate_confidence(),
        },
        "required_tier": {"tier": tier, "reason": reason},
        "flags": {
            "symbiosis_canary": iv.symbiosis_canary_tripped(),
            "seventh_gen_escalation": iv.seventh_gen_escalation(),
            "angels_advocate": iv.angels_advocate_flag(),
        },
        "weights": iv.weights,
        "peig_lenses": {d: PEIG_LENS[d] for d in DIMENSIONS},
    }


# ─── Templates: starting-point matrices for common action shapes ────────────


def empty_iv(action_label: str) -> ImpactVector:
    """Return an unfilled IV — useful as a starting point for the planner."""
    return ImpactVector(action_label=action_label)


def conservative_default_iv(action_label: str) -> ImpactVector:
    """An IV pre-filled with low-confidence zeros across all 12 cells.

    Useful when the model has insufficient context — reflects 'we don't know
    enough to score this with confidence.' Better than emitting no IV at all
    because it makes the absence-of-knowledge auditable.
    """
    iv = ImpactVector(action_label=action_label)
    for dim in DIMENSIONS:
        for scale in SCALES:
            iv.set_cell(ImpactCell(
                dimension=dim,
                scale=scale,
                score=0.0,
                confidence=0.1,  # Very low — flag this as "not really scored"
                notes="default — insufficient context",
            ))
    return iv
