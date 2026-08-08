"""
qa/quality_score.py — Reduce structured reports to a single 0-100 number.

Quality scores are a *summary*, not a substitute for the underlying report.
The operator should still read the failures list and the failing hardening
checks. The number is what you put in a dashboard or a release note.

Design:

  * Two scoring functions: one for TestReport, one for HardeningReport.
  * Each returns a ``QualityScore`` with the same shape: ``value`` (0-100),
    ``grade`` (letter), ``band`` (short label), ``breakdown`` (dimension
    contributions summing to ``value``), and ``notes`` (short explanations).
  * Pure functions. No I/O. Deterministic.
  * Scoring is intentionally **conservative**: a single failure costs
    real points. The grading curve is steep. If you want an A you have
    to earn it; if you want an A+ you have to be flawless.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QualityScore:
    """A 0-100 quality summary with a letter grade and a breakdown.

    ``value`` is the final score. ``breakdown`` is the per-dimension
    contributions and should approximately sum to ``value``. ``notes``
    are short human-readable strings explaining the score.
    """
    value: float                                          # 0-100
    grade: str                                            # A+, A, B, C, D, F
    band: str                                             # short verbal label
    source: str                                           # "test_report" | "hardening_report"
    breakdown: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"quality score · {self.source} · {self.value:.1f}/100 · "
            f"grade {self.grade} · {self.band}",
        ]
        if self.breakdown:
            lines.append("  breakdown:")
            for dim, contrib in self.breakdown.items():
                lines.append(f"    {dim:<24} {contrib:6.1f}")
        if self.notes:
            lines.append("  notes:")
            for n in self.notes:
                lines.append(f"    · {n}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": round(self.value, 2),
            "grade": self.grade,
            "band": self.band,
            "source": self.source,
            "breakdown": {k: round(v, 2) for k, v in self.breakdown.items()},
            "notes": list(self.notes),
        }


def _letter_grade(value: float) -> tuple[str, str]:
    """Return (letter, band) for a 0-100 score.

    The curve is steep on purpose: 'B' means 'has real defects'.
    """
    if value >= 97:
        return "A+", "excellent"
    if value >= 93:
        return "A", "very good"
    if value >= 87:
        return "A-", "good"
    if value >= 80:
        return "B", "acceptable"
    if value >= 70:
        return "C", "needs work"
    if value >= 55:
        return "D", "poor"
    return "F", "broken"


def score_test_report(report: Any) -> QualityScore:
    """Score a ``TestReport`` from qa/runner.py on a 0-100 scale.

    Dimensions (max contributions):
      * pass_rate ......... 60   (fraction of non-skipped tests that passed)
      * no_failures ....... 20   (penalty proportional to failure count)
      * no_errors ......... 10   (errors are worse than failures — harness broke)
      * test_population ....10   (a suite with 0 tests scores 0 here)

    Total: 100.
    """
    breakdown: dict[str, float] = {}
    notes: list[str] = []

    # pass_rate: 60 * (fraction of non-skipped passes)
    pass_rate = float(getattr(report, "pass_rate", 0.0) or 0.0)
    pass_contrib = 60.0 * pass_rate
    breakdown["pass_rate"] = pass_contrib

    # no_failures: 20 points minus 4 per failure (capped at 0)
    failed = int(getattr(report, "failed", 0) or 0)
    fail_contrib = max(0.0, 20.0 - 4.0 * failed)
    breakdown["no_failures"] = fail_contrib
    if failed:
        notes.append(f"{failed} failing test(s)")

    # no_errors: 10 points minus 5 per error (capped at 0)
    errored = int(getattr(report, "errored", 0) or 0)
    err_contrib = max(0.0, 10.0 - 5.0 * errored)
    breakdown["no_errors"] = err_contrib
    if errored:
        notes.append(f"{errored} errored test(s) — likely harness issue")

    # test_population: scale 0 → 0pts, 1-19 → linear, 20+ → 10pts
    total = int(getattr(report, "total", 0) or 0)
    if total <= 0:
        pop_contrib = 0.0
        notes.append("no tests discovered")
    elif total >= 20:
        pop_contrib = 10.0
    else:
        pop_contrib = 10.0 * (total / 20.0)
    breakdown["test_population"] = pop_contrib

    value = sum(breakdown.values())
    value = max(0.0, min(100.0, value))
    grade, band = _letter_grade(value)

    if not notes:
        notes.append(f"{total} test(s), all passing")

    return QualityScore(
        value=value,
        grade=grade,
        band=band,
        source="test_report",
        breakdown=breakdown,
        notes=notes,
    )


def score_hardening_report(report: Any) -> QualityScore:
    """Score a ``HardeningReport`` from qa/hardening.py on a 0-100 scale.

    Dimensions (max contributions):
      * weighted_score .... 65   (sum of passed weights / sum of all weights)
      * critical_checks ... 25   (every weight-≥8 check passes)
      * full_coverage ..... 10   (fraction of checks that passed)

    Total: 100.

    A module that fails a single critical check cannot exceed ~75 here.
    That's the intended behaviour: tier-3 channels missing idempotency
    should NOT score in the A range.
    """
    breakdown: dict[str, float] = {}
    notes: list[str] = []

    checks: list[Any] = list(getattr(report, "checks", []) or [])

    # weighted_score: 65 points × weighted fraction
    weighted = float(getattr(report, "weighted_score", 0.0) or 0.0)
    weighted_contrib = 65.0 * weighted
    breakdown["weighted_score"] = weighted_contrib

    # critical_checks: 25 points if every weight-≥8 check passes
    critical = [c for c in checks if int(getattr(c, "weight", 0)) >= 8]
    crit_failed = [c for c in critical if not getattr(c, "passed", False)]
    if not critical:
        crit_contrib = 0.0
        notes.append("no critical (weight ≥ 8) checks defined")
    elif not crit_failed:
        crit_contrib = 25.0
    else:
        # Lose 8 per critical failure, floor at 0
        crit_contrib = max(0.0, 25.0 - 8.0 * len(crit_failed))
        for c in crit_failed:
            name = getattr(c, "label", None) or getattr(c, "name", "?")
            w = int(getattr(c, "weight", 0))
            notes.append(f"critical check failed: {name} (weight {w})")
    breakdown["critical_checks"] = crit_contrib

    # full_coverage: 10 points × fraction of checks passing
    if checks:
        frac = sum(1 for c in checks if getattr(c, "passed", False)) / len(checks)
    else:
        frac = 0.0
    cov_contrib = 10.0 * frac
    breakdown["full_coverage"] = cov_contrib

    if not checks:
        notes.append("hardening report has zero checks")
    elif not notes:
        notes.append(f"all {len(checks)} hardening check(s) passed")

    value = sum(breakdown.values())
    value = max(0.0, min(100.0, value))
    grade, band = _letter_grade(value)

    return QualityScore(
        value=value,
        grade=grade,
        band=band,
        source="hardening_report",
        breakdown=breakdown,
        notes=notes,
    )
