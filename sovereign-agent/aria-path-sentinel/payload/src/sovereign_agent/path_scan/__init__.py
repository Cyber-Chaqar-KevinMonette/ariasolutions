"""path_scan — god-tier path / anti-ghost / anti-zombie scanner for staged modules.

Catches the "test path left in a new module" family of defects before a module
is applied into live src/. Pure-stdlib; propose-only. Staged; applied via
apply_path_scan.sh, which also registers PathSentinel with the stewardship registry.
"""
from __future__ import annotations

# Force `sovereign_agent.stewardship` to fully resolve before anything reaches
# `path_scan.sentinel` (which is imported BY stewardship/__init__.py to register
# PathSentinel — a bidirectional coupling). Without this, whichever side is
# touched FIRST wins: if path_scan.sentinel is imported before stewardship has
# ever been touched, stewardship's own init runs reentrant mid-way through
# path_scan.sentinel's own import, and fails to pull PathSentinel from what is
# still a partially-initialized module. Importing stewardship here — from
# path_scan's OWN package init, which does not import .sentinel itself — always
# resolves cleanly and gives stewardship a chance to fully initialize first,
# regardless of which side of the coupling a caller touches first.
import sovereign_agent.stewardship  # noqa: F401

from .scanner import (
    Finding,
    ScanResult,
    scan_module,
    scan_one,
    scan_repo,
    scan_text,
)

__all__ = [
    "Finding",
    "ScanResult",
    "scan_text",
    "scan_module",
    "scan_one",
    "scan_repo",
]
