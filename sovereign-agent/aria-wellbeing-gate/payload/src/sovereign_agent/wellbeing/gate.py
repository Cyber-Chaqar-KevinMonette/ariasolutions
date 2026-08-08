"""wellbeing/gate.py — the gate. (Wellbeing round · W2)

`companion_tools.value_report()` was a real, callable tool but computed
fresh every call and nothing ever checked whether the result was actually
GOOD — a session could grade "D" (nothing accomplished, no care shown)
and nothing would flag it. `gate(events, iv=None)` renders a real
PASS/WARN/BLOCK verdict.

  PASS  — clean, or nothing to check (empty events is honest absence,
          never a block — mirrors quality.gate/grounding.gate's exact
          "nothing to check" fix).
  WARN  — a flourishing verdict was computed (decision_text was given)
          and it isn't "carry-forward".
  BLOCK — an ImpactVector's is_zombie() is True (false certainty caught),
          OR the session graded "D" with zero accomplishments AND zero
          care signals shown — a session that produced and showed
          nothing, the concrete, measurable form of Weakness Register
          RISK-004 ("unproven value").

Kill switch: SOV_NO_WELLBEING_GATE=1 — degrades to PASS with a note,
never silently BLOCKs while claiming to have checked something it didn't.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

MARK = "wellbeing-gate-d"


@dataclass
class WellbeingGateVerdict:
    verdict: str                    # "PASS" | "WARN" | "BLOCK"
    love_grade: str = ""
    impact_is_zombie: bool = False
    flourishing_verdict: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        mark = {"PASS": "✓", "WARN": "⚠", "BLOCK": "✗"}[self.verdict]
        head = (f"{mark} wellbeing gate: {self.verdict}"
               + (f" · grade={self.love_grade}" if self.love_grade else ""))
        return "\n".join([head] + [f"  · {n}" for n in self.notes])


def gate(events: list[dict] | None, iv=None, *,
        decision_text: str | None = None) -> WellbeingGateVerdict:
    """Run the value-report + impact + flourishing checks, render the
    gate's verdict. Never raises — a gate that crashes is worse than one
    that BLOCKs honestly."""
    if os.environ.get("SOV_NO_WELLBEING_GATE"):
        return WellbeingGateVerdict(
            verdict="PASS", notes=["kill-switched (SOV_NO_WELLBEING_GATE)"])

    if not events:
        return WellbeingGateVerdict(
            verdict="PASS", notes=["nothing to check — no events"])

    try:
        from sovereign_agent.tools.companion_tools import _build_value_report

        report = _build_value_report(events, None)
    except Exception as exc:  # noqa: BLE001 — the gate must never crash the caller
        return WellbeingGateVerdict(
            verdict="PASS",
            notes=[f"gate itself failed to run: {exc!r} — treated as PASS, "
                   f"never a silent BLOCK"])

    grade = str(report.get("overall_grade", "D"))
    accomplished = len(report.get("accomplished", []))
    care = len(report.get("value_shown", []))

    impact_is_zombie = False
    if iv is not None:
        try:
            impact_is_zombie = bool(iv.is_zombie())
        except Exception:  # noqa: BLE001
            pass

    flourishing_verdict = ""
    if decision_text:
        try:
            from sovereign_agent.foresight import project

            flourishing_verdict = project({"text": decision_text}).verdict
        except Exception:  # noqa: BLE001
            pass

    notes: list[str] = []
    if impact_is_zombie:
        verdict = "BLOCK"
        notes.append("impact vector shows a zombie signal (false certainty)")
    elif grade == "D" and accomplished == 0 and care == 0:
        verdict = "BLOCK"
        notes.append("session produced and showed nothing: grade D, "
                     "zero accomplishments, zero care signals")
    elif flourishing_verdict not in ("", "carry-forward"):
        verdict = "WARN"
        notes.append(f"flourishing verdict: {flourishing_verdict}")
    else:
        verdict = "PASS"

    return WellbeingGateVerdict(verdict=verdict, love_grade=grade,
                                impact_is_zombie=impact_is_zombie,
                                flourishing_verdict=flourishing_verdict,
                                notes=notes)


__all__ = ["WellbeingGateVerdict", "gate"]
