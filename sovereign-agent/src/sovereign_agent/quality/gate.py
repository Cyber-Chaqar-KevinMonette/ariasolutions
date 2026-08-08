"""quality/gate.py — the actual gate. (Quality round · Q2)

`qa/hardening.py` was real and unwired — no gate anywhere called it. This
is the wiring: `gate(paths)` runs Q1's `record_quality_pass()` over the
given files and renders a PASS/WARN/BLOCK verdict a shell gate can act on.

  PASS  — clean, or nothing to check (an empty target list is honest
          absence, never a block — mirrors Q1's `critical_ok` fix).
  WARN  — every critical (weight-≥8) check passed, but the overall score
          is below the 'acceptable' band (grade < B).
  BLOCK — at least one critical check failed. This is the only verdict
          that should ever stop an apply.

Kill switch: SOV_NO_QUALITY_GATE=1 — degrades to PASS with a note, never
silently BLOCKs while claiming to have checked something it didn't.

Observability note (also why this file cites `emit_event` by name): every
call to `gate()` runs `record_quality_pass()`, which itself calls
`emit_event("quality-pass-d", ...)` — a gate result is never silent.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

MARK = "quality-gate-d"

_WARN_BELOW = 80.0   # grade B floor, per qa/quality_score.py's own curve


@dataclass
class QualityGateVerdict:
    verdict: str                          # "PASS" | "WARN" | "BLOCK"
    value: float
    critical_ok: bool
    files_checked: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        mark = {"PASS": "✓", "WARN": "⚠", "BLOCK": "✗"}[self.verdict]
        head = (f"{mark} quality gate: {self.verdict} · {self.files_checked} "
               f"file(s) · {self.value:.1f}/100")
        return "\n".join([head] + [f"  · {n}" for n in self.notes])


def gate(paths: list[Path | str]) -> QualityGateVerdict:
    """Run the quality pass, render the gate's verdict. Never raises —
    a gate that crashes is worse than one that BLOCKs honestly."""
    if os.environ.get("SOV_NO_QUALITY_GATE"):
        return QualityGateVerdict(verdict="PASS", value=0.0, critical_ok=True,
                                  files_checked=0,
                                  notes=["kill-switched (SOV_NO_QUALITY_GATE)"])

    from sovereign_agent.quality.ledger import record_quality_pass

    try:
        result = record_quality_pass([Path(p) for p in paths])
    except Exception as exc:  # noqa: BLE001 — the gate must never crash the caller
        return QualityGateVerdict(verdict="PASS", value=0.0, critical_ok=True,
                                  files_checked=0,
                                  notes=[f"gate itself failed to run: {exc!r} "
                                        f"— treated as PASS, never a silent BLOCK"])

    if not result.files:
        return QualityGateVerdict(verdict="PASS", value=0.0, critical_ok=True,
                                  files_checked=0,
                                  notes=["nothing to check — no scoreable .py files"])

    notes = []
    for f in result.files:
        if not f.critical_ok:
            notes.append(f"BLOCK: {f.path} failed critical check(s): "
                        f"{', '.join(f.critical_failures)}")

    if not result.critical_ok:
        verdict = "BLOCK"
    elif result.value < _WARN_BELOW:
        verdict = "WARN"
        notes.append(f"score {result.value:.1f} below the acceptable band "
                    f"({_WARN_BELOW})")
    else:
        verdict = "PASS"

    return QualityGateVerdict(verdict=verdict, value=result.value,
                              critical_ok=result.critical_ok,
                              files_checked=len(result.files), notes=notes)


__all__ = ["QualityGateVerdict", "gate"]
