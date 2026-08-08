"""godtier/rubric.py — score a target against the god-tier canon (scripts/lib/god_tier_canon.json).

Cheap, static, honest scoring: presence of tests/docs/apply, debug-free, error-handling, non-classical
parity flag. Emits a 0..1 god-tier score, a band (god_tier/strong/fragile/weak/neglected), and the named
gaps. The scanner ranks by score; the weakest + most-neglected surface first. No hype: a missing test is a
named gap, not a vibe.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _canon() -> dict:
    # find scripts/lib/god_tier_canon.json from this file or cwd
    for base in (Path(__file__).resolve(), Path.cwd()):
        for up in [base, *base.parents]:
            cand = up / "scripts" / "lib" / "god_tier_canon.json"
            if cand.exists():
                return json.loads(cand.read_text(encoding="utf-8"))
    return {"score_bands": {"god_tier": [0.85, 1.0], "strong": [0.7, 0.85], "fragile": [0.5, 0.7],
                            "weak": [0.3, 0.5], "neglected": [0.0, 0.3]}}


def band_for(score: float) -> str:
    bands = _canon().get("score_bands", {})
    for name, (lo, hi) in bands.items():
        if lo <= score <= hi:
            return name
    return "neglected" if score < 0.3 else "strong"


# Per-kind criteria → (signal key, gap message). Each is worth 1 point.
_CRITERIA = {
    "module": [
        ("has_payload", "no payload (doc/script-only — confirm intended)"),
        ("has_tests", "no tests (add behavioral tests that prove it WORKS)"),
        ("has_readme", "no README (document what it gives, honestly)"),
        ("has_apply", "no apply script (reversibility: how is it applied + rolled back?)"),
        ("no_debug", "debugger/breakpoint left in payload (cleanliness)"),
        ("error_handling", "no error handling found (robustness)"),
        ("has_docstrings", "thin docstrings (documenting)"),
    ],
    "layer": [
        ("has_tests", "no tests found for this core layer"),
        ("no_debug", "debugger left in the layer (cleanliness)"),
        ("error_handling", "little error handling (robustness)"),
        ("has_docstrings", "thin docstrings"),
    ],
    "doc": [
        ("present", "missing"),
        ("nonempty", "empty/stub"),
    ],
}


def score_target(target) -> dict:
    """Return {score, band, gaps, met, total} for a target."""
    kind = target.kind if hasattr(target, "kind") else target.get("kind")
    sig = target.signals if hasattr(target, "signals") else target.get("signals", {})
    crit = _CRITERIA.get(kind, _CRITERIA["module"])
    met, gaps = 0, []
    for key, msg in crit:
        if sig.get(key):
            met += 1
        else:
            gaps.append(msg)
    total = len(crit)
    score = met / total if total else 1.0
    # non-classical parity: a quantum layer with tests is honored; without, flagged hard
    if sig.get("is_non_classical") and not sig.get("has_tests"):
        gaps.append("NON-CLASSICAL PARITY: the non-classical layer must be tested to god-tier parity")
        score = min(score, 0.49)
    tid = target.id if hasattr(target, "id") else target.get("id")
    return {"id": tid, "kind": kind, "score": round(score, 3), "band": band_for(score),
            "met": met, "total": total, "gaps": gaps}
