"""integrity/gate.py — the live, standing gate. (Integrity round · I2)

Same shape as `grounding/gate.py`: a LIVE, one-shot check over given text —
distinct from `ledger.py`'s persisted history (which a sentinel writes to
standing, `integrity_sentinel.py` in I3). `gate()` does not itself write
to the ledger — mirrors `grounding.gate()` exactly: the gate is what
`pre_apply_gate.sh` calls per-proposal; the ledger is what the standing
sentinel accumulates over time.

  PASS  — every available signal reads clean, or nothing to check.
  WARN  — a single signal concerns while the rest pass.
  BLOCK — the worst-of composite genuinely fails (mirrors each signal's
          own existing narrow BLOCK condition — this doesn't invent a new
          threshold, it composes the existing ones).

Kill switch: SOV_NO_INTEGRITY_GATE=1 — degrades to PASS with a note, never
silently BLOCKs while claiming to have checked something it didn't.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .ledger import _score_grounding, _score_identity, _score_outcome_calibration, _score_witness

MARK = "integrity-gate-d"

_RANK = {"ok": 0, "concern": 1, "fail": 2}


@dataclass
class IntegrityGateVerdict:
    verdict: str   # "PASS" | "WARN" | "BLOCK"
    value: float
    signals: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        mark = {"PASS": "✓", "WARN": "⚠", "BLOCK": "✗"}[self.verdict]
        head = f"{mark} integrity gate: {self.verdict} · {self.value:.2f}"
        return "\n".join([head] + [f"  · {n}" for n in self.notes])


def gate(text: str, *, claimed_confidence: float | None = None,
         predicted_impact=None, actual_impact=None,
         data_dir: Path | None = None) -> IntegrityGateVerdict:
    """Run the four signals LIVE (never writing to the ledger — that's the
    sentinel's job), render a worst-of verdict. Never raises."""
    if os.environ.get("SOV_NO_INTEGRITY_GATE"):
        return IntegrityGateVerdict(
            verdict="PASS", value=0.0,
            notes=["kill-switched (SOV_NO_INTEGRITY_GATE)"])

    signals = [
        _score_grounding(text, claimed_confidence),
        _score_outcome_calibration(predicted_impact, actual_impact),
        _score_witness(text),
        _score_identity(data_dir),
    ]
    scored = [s for s in signals if s.available]
    notes = [f"{s.name}: {s.detail}" for s in scored if s.verdict != "ok"]

    if not scored:
        return IntegrityGateVerdict(
            verdict="PASS", value=0.0, signals=[s.as_dict() for s in signals],
            notes=["nothing to check"])

    value = round(sum(s.score for s in scored) / len(scored), 3)
    worst = max((s.verdict for s in scored), key=lambda v: _RANK.get(v, 0))
    verdict = {"ok": "PASS", "concern": "WARN", "fail": "BLOCK"}[worst]

    return IntegrityGateVerdict(
        verdict=verdict, value=value, signals=[s.as_dict() for s in signals], notes=notes)


__all__ = ["IntegrityGateVerdict", "gate"]
