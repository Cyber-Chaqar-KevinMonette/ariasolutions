"""foresight/ultimate_questions.py — the 400 Ultimate Questions, baked in (honestly tiered).

Kevin's Gen-7→100 north star (Plan2Examin/UltimateQuestionsOfAllTimeV2.md), parsed into a queryable
catalog. Each question is tagged by part/domain and an honest tier:

    actionable-now        — maps to real near-term engineering (safety, source, cryptography, Gen 8–14)
    near-term             — plausible mid-horizon (bio/orbital/ASIC) — vision with an engineering seam
    north-star-reflection — cosmic (stellar → Omega Point): honored as VISION, never claimed as built

This is a REFLECTION corpus, not a build list. Aria consults it during foresight/horizon scans to keep
the long view — with humility. The Tribunal scrutinizes any output that treats the cosmic items as done.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "ultimate_questions.json"

ACTIONABLE, NEAR, NORTH_STAR = "actionable-now", "near-term", "north-star-reflection"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not _DATA.exists():
        return {"count": 0, "questions": []}
    return json.loads(_DATA.read_text(encoding="utf-8"))


def all_questions() -> list[dict]:
    return list(_load().get("questions", []))


def count() -> int:
    return _load().get("count", 0)


def by_tier(tier: str) -> list[dict]:
    return [q for q in all_questions() if q["tier"] == tier]


def by_part(part: int) -> list[dict]:
    return [q for q in all_questions() if q["part"] == part]


def get(n: int) -> dict | None:
    for q in all_questions():
        if q["n"] == n:
            return q
    return None


def search(keyword: str, *, tier: str | None = None, limit: int = 20) -> list[dict]:
    """Find questions matching a keyword (in text or part title), optionally filtered by tier."""
    kw = keyword.lower().strip()
    out = []
    for q in all_questions():
        if tier and q["tier"] != tier:
            continue
        if not kw or kw in q["text"].lower() or kw in q["part_title"].lower():
            out.append(q)
        if len(out) >= limit:
            break
    return out


def summary() -> dict:
    qs = all_questions()
    tiers: dict[str, int] = {}
    for q in qs:
        tiers[q["tier"]] = tiers.get(q["tier"], 0) + 1
    return {
        "total": len(qs),
        "by_tier": tiers,
        "parts": len({q["part"] for q in qs}),
        "honest_note": ("These are Kevin's Gen-7→100 north star. The cosmic tier is VISION, never claimed "
                        "as built. Aria consults them for the long view, with humility."),
    }
