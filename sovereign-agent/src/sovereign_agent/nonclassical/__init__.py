"""nonclassical — bring the non-classical (PEIG/quantum) layer to god-tier parity, measured not claimed.

God-tier demands the non-classical hemisphere be as robust as the classical one, and on par or better.
This module proves it:
  robustness.py — determinism · graceful degradation · bounded learning (god-tier hardening checks)
  parity.py     — benchmark the PEIG brain vs a classical baseline on a shared task (honest verdict)
"""
from __future__ import annotations

from . import robustness, parity

__all__ = ["robustness", "parity"]
