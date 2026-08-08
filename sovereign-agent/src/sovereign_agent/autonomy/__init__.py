"""autonomy — Supervised Autonomy Sessions: time-boxed, observable, resumable, bounded.

Aria plans, the human approves a bounded block (~90 min), she works inside a tight blast-radius (staged
drafting / verify / scrutiny only — never outward, never sealed, never apply), then pauses with a resumable
checkpoint. The human stays present, watching and learning. God-tier safety: bounded · observable ·
reversible · always-stoppable.

  session.py    — the lease, the bounded action set, pause/resume, the observation log
  plan_forge.py — living, versioned plans that grow over time even as she works
"""
from __future__ import annotations

from . import session, plan_forge

__all__ = ["session", "plan_forge"]
