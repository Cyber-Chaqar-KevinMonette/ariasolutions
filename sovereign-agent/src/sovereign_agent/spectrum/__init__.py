"""spectrum — the god-tier advocate/audit SPECTRUM (a council of ten perspectives).

The 3-voice Tribunal (Devil · Angel · Audit) becomes a council: + Skeptic · Steward · Witness · Sage ·
Healer · Artisan · Visionary. Each lens reads a proposal through one perspective; the council synthesizes
one verdict, richer than any single voice. Safety lenses hold a veto. Propose-only.

  lenses.py  — the ten perspectives    council.py — convene_spectrum() → CouncilVerdict
"""
from __future__ import annotations

from . import lenses, council
from .council import convene_spectrum, CouncilVerdict

__all__ = ["lenses", "council", "convene_spectrum", "CouncilVerdict"]
