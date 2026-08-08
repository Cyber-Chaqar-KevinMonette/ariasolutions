"""godtier — Aria's god-tier system scanner (her inner eye).

Holds the whole system to GOD_TIER_CANON.md: enumerates every target, scores each against the rubric,
surfaces every weak/fragile/neglected/sub-god-tier system transparently, and drafts propose-only
enhancements. Total coverage — nothing is neglected.

  targets.py — enumerate everything    rubric.py — score vs the canon
  scanner.py — rank the weakest, report    enhance.py — draft propose-only fixes
"""
from __future__ import annotations

from . import targets, rubric, scanner, enhance

__all__ = ["targets", "rubric", "scanner", "enhance"]
