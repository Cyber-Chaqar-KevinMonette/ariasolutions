"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/plan.py — Plan / ExecutionWitness / Impact triple            ║
║  v0.2.20.0                                                                ║
║                                                                           ║
║  Every piece of work Aria does produces a triple:                        ║
║                                                                           ║
║    Plan                — written BEFORE execution                        ║
║      What she'll do, what she predicts, where she could fail, how to    ║
║      roll back. The plan is the perception of the work BEFORE doing it. ║
║                                                                           ║
║    ExecutionWitness    — observed DURING execution                       ║
║      What actually happened, surprises (positive or negative), what she ║
║      almost missed, the texture of doing the work. The witness is the   ║
║      perception of the work AS doing it.                                 ║
║                                                                           ║
║    ImpactVector        — measured AFTER execution                        ║
║      The MSIMS v2 IV scored against reality. The IV is the perception   ║
║      of the work AFTER doing it.                                         ║
║                                                                           ║
║  These three together = a StewardshipTriple — a complete record of one  ║
║  piece of work, witnessed three times from three angles. The triples    ║
║  are durable; they become Knowledge Atoms.                              ║
║                                                                           ║
║  Why a triple, not just a result:                                        ║
║                                                                           ║
║    Calibration is the diff between Plan.predicted_iv and Impact.actual_iv.║
║    If Aria predicted high harm and got low harm: over-caution.           ║
║    If Aria predicted low harm and got high harm: false certainty.       ║
║    If Aria predicted accurately: trustworthy perception.                ║
║                                                                           ║
║    Calibration is the reward signal. Aria doesn't get points for big    ║
║    impact — she gets points for predicting her own impact accurately.   ║
║    This trains perception, not boasting.                                ║
║                                                                           ║
║  Doctrinal anchor:                                                       ║
║    MOS Architect-Auditor — "calibrated uncertainty" Behavioral Law 5    ║
║    MSIMS v2 — "false certainty earns the harshest penalty"              ║
║    PIAL — anti-zombie discipline                                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from .msims import (
    Cell,
    Dimension,
    Horizon,
    ImpactVector,
    Reversibility,
    Scale,
)


# ─── Plan quality dimensions ────────────────────────────────────────────────


class PlanQualityCheck(StrEnum):
    """The five checks that make a plan production-quality.

    Drawn from MOS Architect-Auditor's Guardrails section:
      • Failure modes named?
      • Rollback defined?
      • Observability present?
      • Authority bounded?
      • Uncertainty calibrated?

    Each check is a binary in the Plan; the Plan's quality score is the
    sum across them. A plan with all five checks is "fully formed."
    A plan with two or fewer is "incomplete" and the router will
    surface a warning to the operator before execution.
    """
    FAILURE_MODES = "failure_modes"
    ROLLBACK = "rollback"
    OBSERVABILITY = "observability"
    AUTHORITY = "authority"
    UNCERTAINTY = "uncertainty"


# ─── Plan ───────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    """The written-down prediction of a piece of work.

    Aria writes one of these BEFORE running commands. The plan is
    structured enough to score (PlanQualityCheck) but loose enough to
    capture the texture of how she's thinking (rationale, notes).

    The predicted_iv is Aria's forecast of the IV she expects the
    work to produce. This is the calibration anchor: actual_iv will be
    measured against it after execution.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    summary: str = ""
    commands: list[str] = field(default_factory=list)
    rationale: str = ""

    # The Plan Quality Checks — each is a name + (is_present, text).
    # We don't grade Aria here; the calibration module does.
    failure_modes_named: list[str] = field(default_factory=list)
    rollback_steps: list[str] = field(default_factory=list)   # empty if irreversible
    observability_points: list[str] = field(default_factory=list)
    authority_tier: int = 1
    uncertainty_notes: list[str] = field(default_factory=list)

    # The forecast. confidence on each cell tells us how strongly Aria
    # claims to know. A plan that fills every cell with high confidence
    # is making a strong claim; if reality disagrees, the calibration
    # penalty is correspondingly steep.
    predicted_iv: ImpactVector = field(default_factory=ImpactVector)

    ts_created: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )

    # ── Quality scoring ─────────────────────────────────────────────

    def quality_checks(self) -> dict[PlanQualityCheck, bool]:
        """Which of the five checks does this plan pass?"""
        return {
            PlanQualityCheck.FAILURE_MODES: bool(self.failure_modes_named),
            PlanQualityCheck.ROLLBACK: (
                bool(self.rollback_steps)
                or self._is_explicitly_irreversible()
            ),
            PlanQualityCheck.OBSERVABILITY: bool(self.observability_points),
            PlanQualityCheck.AUTHORITY: 0 <= self.authority_tier <= 4,
            PlanQualityCheck.UNCERTAINTY: bool(self.uncertainty_notes),
        }

    def _is_explicitly_irreversible(self) -> bool:
        """Rollback may legitimately be empty if the plan explicitly
        names the work as irreversible — irreversibility is acknowledged
        in the predicted IV's cells."""
        for _, _, c in self.predicted_iv.all_cells():
            if c.reversibility == Reversibility.IRREVERSIBLE:
                return True
        return False

    def quality_score(self) -> float:
        """Plan Quality Score ∈ [0, 1]. The fraction of checks passed."""
        checks = self.quality_checks()
        return sum(1.0 for v in checks.values() if v) / len(checks)

    def is_fully_formed(self) -> bool:
        return self.quality_score() == 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "summary": self.summary,
            "commands": list(self.commands),
            "rationale": self.rationale,
            "failure_modes_named": list(self.failure_modes_named),
            "rollback_steps": list(self.rollback_steps),
            "observability_points": list(self.observability_points),
            "authority_tier": self.authority_tier,
            "uncertainty_notes": list(self.uncertainty_notes),
            "predicted_iv": self.predicted_iv.to_dict(),
            "ts_created": self.ts_created,
            "quality_score": self.quality_score(),
        }


# ─── Execution Witness ──────────────────────────────────────────────────────


@dataclass
class ExecutionWitness:
    """What Aria observed DURING execution.

    This is the texture of the work — the in-flight perception. Most
    fields are optional; the witness is permissive because the work is
    the point. But two fields earn structural attention:

        almost_missed: things Aria noticed she'd nearly overlooked.
            These are the highest-leverage Honor signals. Capturing
            "I almost shipped this without checking X" is more
            valuable than capturing the work itself.

        surprises: gaps between Plan.predicted_iv and what reality
            looked like along the way. These are the raw material for
            calibration.
    """
    plan_id: str = ""
    executed_commands: list[str] = field(default_factory=list)
    exit_codes: list[int] = field(default_factory=list)
    duration_seconds: float = 0.0

    surprises: list[str] = field(default_factory=list)
    almost_missed: list[str] = field(default_factory=list)
    in_flight_notes: list[str] = field(default_factory=list)

    ts_started: str = ""
    ts_finished: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── The full triple ────────────────────────────────────────────────────────


@dataclass
class StewardshipTriple:
    """Plan + Witness + Impact = one complete record of a piece of work.

    The triple is what gets saved as a Knowledge Atom. It carries
    enough structure for replay, calibration, audit, and future
    pattern-mining over Aria's history of work.
    """
    plan: Plan
    witness: ExecutionWitness
    actual_iv: ImpactVector

    @property
    def succeeded(self) -> bool:
        """All commands exited 0."""
        return bool(self.witness.exit_codes) and all(
            c == 0 for c in self.witness.exit_codes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "witness": self.witness.to_dict(),
            "actual_iv": self.actual_iv.to_dict(),
            "succeeded": self.succeeded,
        }

    def to_atom(self) -> dict[str, Any]:
        """Render as a Knowledge Atom in the MOS-canonical shape.

        The atom is what becomes durable. Future audits replay these,
        retrieval surfaces them, and Aria can look at her own work
        across time by querying this atom type.
        """
        return {
            "atom_id": self.plan.plan_id,
            "type": "decision",
            "scope": {
                "path": "stewardship/triple",
                "tags": [
                    "msims-v2",
                    f"tier-{self.plan.authority_tier}",
                    "succeeded" if self.succeeded else "failed",
                ],
            },
            "summary": (
                f"{self.plan.summary} — "
                f"IS_7g: {self.actual_iv.is_7g():.2f}"
            ),
            "claims": [
                {
                    "predicate": f"{d}_{s}",
                    "value": c.value,
                    "confidence": c.confidence,
                    "horizon": str(c.horizon),
                    "reversibility": str(c.reversibility),
                    "evidence_ref": c.evidence,
                }
                for (d, s), c in self.actual_iv.cells.items()
            ],
            "data": self.to_dict(),
            "ts": self.actual_iv.ts,
        }


# ─── Persistence ────────────────────────────────────────────────────────────


def save_triple(triple: StewardshipTriple, root: Path) -> Path:
    """Persist one triple as a JSON file under the stewardship dir.

    Atomic write via temp + rename. The filename embeds the plan_id
    so it's uniquely retrievable and globbing returns chronological
    order if the operator sorts by mtime.
    """
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{triple.plan.plan_id}.json"
    tmp = root / f".{triple.plan.plan_id}.json.tmp"
    tmp.write_text(
        json.dumps(triple.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    tmp.replace(target)
    return target


def load_triple(path: Path) -> dict[str, Any]:
    """Re-hydrate a triple from disk as a plain dict.

    Returns the dict rather than the dataclasses so the caller can
    decide how richly to re-construct (full objects vs. read-only
    inspection). Triples are append-only — we don't mutate stored
    files.
    """
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "Plan",
    "PlanQualityCheck",
    "ExecutionWitness",
    "StewardshipTriple",
    "save_triple",
    "load_triple",
]
