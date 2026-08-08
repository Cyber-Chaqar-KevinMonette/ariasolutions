"""foresight — Aria's generational foresight + the Ultimate Questions baked in.

  ultimate_questions.py — the 400 Gen-7→100 questions, queryable + honestly tiered (cosmic = vision)
  foresight.py          — the 14-generation projection engine: intergenerational equity, lock-in,
                          value-drift, reversibility, then north-star reflection

"Think 14 generations ahead." Structured foresight, not prophecy. Propose-only.
"""
from __future__ import annotations

from . import ultimate_questions, foresight
from .foresight import project, Foresight, GENERATIONS

__all__ = ["ultimate_questions", "foresight", "project", "Foresight", "GENERATIONS"]
