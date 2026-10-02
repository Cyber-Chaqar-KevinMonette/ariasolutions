"""maturity/report.py — how well is she self-managing? Measured from the stored mood ledger only.

Maturity here is observable behavior over time, not a self-rating:
- **steadiness:** average change per update across all dimensions (lower = steadier)
- **recovery:** after a hard stretch (concern > 0.5 or fatigue > 0.6), how many updates until she's back
- **balance:** dimensions pinned at an extreme (< 0.05 or > 0.95) — a healthy system stays off the rails
- **ownership:** corrective entries that were logged with evidence (owning mistakes is mature)
- **engaged:** share of updates where she was working (tool activity) and not strained
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .mood import DIMENSIONS


@dataclass
class MaturityReport:
    updates: int
    steadiness: float | None          # mean |Δ| per dimension per update
    recovery_updates: float | None    # mean updates to recover from a hard stretch
    hard_stretches: int
    pinned_dimensions: list[str]
    ownership: int
    engaged_share: float | None
    summary: str

    def as_dict(self) -> dict:
        return asdict(self)


def _hard(dims: dict) -> bool:
    return dims.get("concern", 0) > 0.5 or dims.get("fatigue", 0) > 0.6


def maturity_report(history: list[dict]) -> MaturityReport:
    """Build the report from mood-ledger records (oldest first)."""
    if not isinstance(history, list):
        raise ValueError("history must be a list of mood records")
    moods = [h["mood"]["dims"] for h in history if "mood" in h]
    n = len(moods)
    if n < 2:
        return MaturityReport(n, None, None, 0, [], 0, None,
                              "Not enough history yet. Maturity shows over time, not in one check-in.")
    deltas = [abs(b[d] - a[d]) for a, b in zip(moods, moods[1:], strict=False) for d in DIMENSIONS]
    steadiness = round(sum(deltas) / len(deltas), 4)

    recoveries, stretches, i = [], 0, 0
    while i < n:
        if _hard(moods[i]):
            stretches += 1
            j = i
            while j < n and _hard(moods[j]):
                j += 1
            if j < n:
                recoveries.append(j - i)
            i = j
        else:
            i += 1
    recovery = round(sum(recoveries) / len(recoveries), 2) if recoveries else None

    last = moods[-1]
    pinned = [d for d in DIMENSIONS if last.get(d, 0.5) < 0.05 or last.get(d, 0.5) > 0.95]
    ownership = sum(len(h.get("lessons", [])) for h in history)
    engaged = [bool(h.get("signals", {}).get("tool_event_count")) and not _hard(h["mood"]["dims"])
               for h in history if "mood" in h]
    engaged_share = round(sum(engaged) / len(engaged), 3) if engaged else None

    if pinned:
        from . import safe_emit_event

        safe_emit_event("maturity.dimension_pinned", dimensions=pinned)
    if stretches and recovery is None:
        summary = "In a hard stretch now. The priority is recovery: pace, report, smallest next step."
    elif steadiness <= 0.05 and not pinned:
        tail = f"; recovers from hard stretches in ~{recovery} updates." if recovery else "."
        summary = "Steady and balanced" + tail
    elif pinned:
        summary = f"Pinned at an extreme: {', '.join(pinned)}. Worth a look with Kevin."
    else:
        summary = "Moving, but within healthy bounds."
    return MaturityReport(n, steadiness, recovery, stretches, pinned, ownership, engaged_share, summary)
