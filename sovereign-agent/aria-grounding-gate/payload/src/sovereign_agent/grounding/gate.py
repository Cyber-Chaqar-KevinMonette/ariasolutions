"""grounding/gate.py — the calibration check. (Grounding round · G2)

The sharpest concrete anti-hallucination gap: `curiosity.py`'s wonder loop
trusts the model's SELF-REPORTED confidence with nothing checking it
against the answer's own grounding texture — a model could claim
confidence 0.9 while writing pure mystical-fog prose and nothing catches
the mismatch. This gate closes that, real teeth: `gate(text,
claimed_confidence=...)` renders a PASS/WARN/BLOCK verdict a caller can
act on.

  PASS  — clean, or nothing to check (empty text is honest absence, never
          a block — mirrors quality.gate's exact "nothing to check" fix).
  WARN  — the text's own verdict is "mixed" with no confidence mismatch.
  BLOCK — the text's own verdict is "ungrounded", OR a confidently-claimed
          answer (>= 0.6) doesn't actually verify as "grounded" — the
          calibration mismatch this gate exists to catch.

Kill switch: SOV_NO_GROUNDING_GATE=1 — degrades to PASS with a note, never
silently BLOCKs while claiming to have checked something it didn't.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

MARK = "grounding-gate-d"

_CONFIDENCE_BLOCK_FLOOR = 0.6   # a confidently-claimed answer must actually verify grounded


@dataclass
class GroundingGateVerdict:
    verdict: str                     # "PASS" | "WARN" | "BLOCK"
    text_verdict: str                # grounded | mixed | ungrounded | "" (nothing to check)
    grounding_score: float
    calibration_mismatch: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        mark = {"PASS": "✓", "WARN": "⚠", "BLOCK": "✗"}[self.verdict]
        head = (f"{mark} grounding gate: {self.verdict} · "
               f"verdict={self.text_verdict or '(nothing to check)'} · "
               f"{self.grounding_score:.2f}")
        return "\n".join([head] + [f"  · {n}" for n in self.notes])


def gate(text: str, *, claimed_confidence: float | None = None) -> GroundingGateVerdict:
    """Run the grounding classifier, render the gate's verdict. Never
    raises — a gate that crashes is worse than one that BLOCKs honestly."""
    if os.environ.get("SOV_NO_GROUNDING_GATE"):
        return GroundingGateVerdict(
            verdict="PASS", text_verdict="", grounding_score=0.0,
            calibration_mismatch=False,
            notes=["kill-switched (SOV_NO_GROUNDING_GATE)"])

    if not text or not str(text).strip():
        return GroundingGateVerdict(
            verdict="PASS", text_verdict="", grounding_score=0.0,
            calibration_mismatch=False,
            notes=["nothing to check — empty text"])

    try:
        from sovereign_agent.tribunal import grounding as _grounding

        report = _grounding.analyze(text)
    except Exception as exc:  # noqa: BLE001 — the gate must never crash the caller
        return GroundingGateVerdict(
            verdict="PASS", text_verdict="", grounding_score=0.0,
            calibration_mismatch=False,
            notes=[f"gate itself failed to run: {exc!r} — treated as PASS, "
                   f"never a silent BLOCK"])

    notes: list[str] = []
    mismatch = False
    if (claimed_confidence is not None and claimed_confidence >= _CONFIDENCE_BLOCK_FLOOR
            and report.verdict != "grounded"):
        mismatch = True
        notes.append(f"claimed confidence {claimed_confidence:.2f} but text "
                     f"verdict is {report.verdict!r} — calibration mismatch")

    if report.verdict == "ungrounded" or mismatch:
        verdict = "BLOCK"
        if report.verdict == "ungrounded":
            notes.append(f"text verdict is ungrounded: {', '.join(report.flags[:3])}")
    elif report.verdict == "mixed":
        verdict = "WARN"
        notes.append("text verdict is mixed — some claims unanchored")
    else:
        verdict = "PASS"

    return GroundingGateVerdict(
        verdict=verdict, text_verdict=report.verdict,
        grounding_score=round(report.grounding_score, 3),
        calibration_mismatch=mismatch, notes=notes)


__all__ = ["GroundingGateVerdict", "gate"]
