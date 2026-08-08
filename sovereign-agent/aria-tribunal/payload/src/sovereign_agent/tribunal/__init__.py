"""tribunal — Aria's god-tier scrutiny system (Devil · Angel · Audit + synthesizer).

Three independent voices over any non-trivial work, then a verdict:
  - grounding.py — the antidote to ungrounded profundity (classifies assertions, scores fog)
  - devil.py     — Devil's Advocate: hunts what breaks (severity-scored findings)
  - angel.py     — Angel's Advocate: names what's worth protecting; critique → paths forward
  - audit.py     — independent evidence verification (facts, not opinions)
  - tribunal.py  — the synthesizer: convene() → Verdict; gates Ring-2 improvements; logs to diagnosis

Propose-only. The operator acts. Operationalizes the MOS canon advocate/audit clauses as running engines.
"""
from __future__ import annotations

from . import grounding, devil, angel, audit, tribunal
from .tribunal import convene, gate_ring2_improvement, Verdict

__all__ = ["grounding", "devil", "angel", "audit", "tribunal",
           "convene", "gate_ring2_improvement", "Verdict"]
