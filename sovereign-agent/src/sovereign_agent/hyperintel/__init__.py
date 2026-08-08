"""hyperintel — the HyperIntel research faculty: a bounded QUESTION -> SCAN ->
CROSS -> AUDIT -> DISTILL loop over caller-supplied sources. Never fetches new
sources on its own initiative — bounded, propose-only. Staged; applied via
apply_hyperintel.sh."""
from __future__ import annotations

from sovereign_agent.hyperintel.engine import (
    Claim,
    HyperIntelReport,
    Source,
    audit,
    cross_validate,
    distill,
    run,
    scan,
)

__all__ = [
    "Source", "Claim", "HyperIntelReport",
    "scan", "cross_validate", "audit", "distill", "run",
]
