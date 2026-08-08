"""scanner_tier_a — the 6 Tier-A scanners from SCANNER_CATALOG.md, built on D's
scan-engine discipline. Plugs into H1's Universal Scanner Kernel fan-out once both
are applied. Staged; applied via apply_scanner_tier_a.sh."""
from __future__ import annotations

from sovereign_agent.scanner_tier_a.scanner import (
    Finding,
    ScanResult,
    scan_all_exports,
    scan_anchor_integrity,
    scan_authority_tier_drift,
    scan_bare_except,
    scan_file,
    scan_import_cycles,
    scan_mutable_defaults,
    scan_secrets,
    scan_tree,
)

__all__ = [
    "Finding", "ScanResult",
    "scan_secrets", "scan_anchor_integrity", "scan_all_exports",
    "scan_import_cycles", "scan_authority_tier_drift",
    "scan_bare_except", "scan_mutable_defaults",
    "scan_file", "scan_tree",
]
