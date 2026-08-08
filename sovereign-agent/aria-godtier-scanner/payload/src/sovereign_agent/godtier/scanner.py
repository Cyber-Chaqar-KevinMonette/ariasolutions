"""godtier/scanner.py — hold the whole system to the canon; rank the weakest; report everything.

Her inner eye. Scans every target, scores each against the rubric, and surfaces — transparently — every
weak / fragile / neglected / sub-god-tier system, ranked worst-first. Total coverage is the mandate:
nothing is neglected, because everything is scanned and named. Propose-only.
"""
from __future__ import annotations

from pathlib import Path

from . import targets as _targets
from . import rubric as _rubric


def scan(repo: Path | None = None) -> dict:
    """Score every target; return the full report (coverage + bands + ranked weakest)."""
    repo = Path(repo) if repo else Path.cwd()
    tgts = _targets.enumerate_targets(repo)
    scored = [_rubric.score_target(t) for t in tgts]
    scored.sort(key=lambda s: s["score"])   # weakest first

    bands: dict[str, int] = {}
    for s in scored:
        bands[s["band"]] = bands.get(s["band"], 0) + 1
    n = len(scored) or 1
    avg = round(sum(s["score"] for s in scored) / n, 3)
    god_tier_frac = round(sum(1 for s in scored if s["band"] == "god_tier") / n, 3)

    return {
        "total_targets": len(scored),
        "average_score": avg,
        "god_tier_fraction": god_tier_frac,
        "bands": bands,
        "weakest": scored[:15],
        "all": scored,
        "mandate": "Total coverage — anything unscanned is itself a gap. Nothing is neglected.",
    }


def gaps(repo: Path | None = None, *, max_band: str = "fragile") -> list[dict]:
    """Targets at or below `max_band` — the things that are not yet god-tier, worst first."""
    order = ["neglected", "weak", "fragile", "strong", "god_tier"]
    cutoff = order.index(max_band) if max_band in order else 2
    rep = scan(repo)
    return [s for s in rep["all"] if s["band"] in order[: cutoff + 1]]


def summary_line(repo: Path | None = None) -> str:
    rep = scan(repo)
    return (f"god-tier scan: {rep['total_targets']} targets · avg {rep['average_score']} · "
            f"{int(rep['god_tier_fraction']*100)}% god-tier · bands {rep['bands']}")
