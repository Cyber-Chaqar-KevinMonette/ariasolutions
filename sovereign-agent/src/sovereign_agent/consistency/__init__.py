"""consistency — the one-truth organ: cross-store joins, checked. (FABLE II · M1)

Staged; applied via apply_consistency.sh. See checks.py for the joins and
sentinel.py for the ConsistencySentinel (warn-level health, propose-only).
"""
from __future__ import annotations

from .checks import ALL_CHECKS, CheckResult, Finding, run_all, symbol_exists

__all__ = ["ALL_CHECKS", "CheckResult", "Finding", "run_all", "symbol_exists"]
