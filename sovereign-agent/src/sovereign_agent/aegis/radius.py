"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/radius.py — blast radius taxonomy                                  ║
║                                                                           ║
║  Every incident gets classified at intake. The classification governs    ║
║  what Aegis is permitted to do autonomously and what it must escalate.  ║
║                                                                           ║
║    R0 — single artifact                                                  ║
║         One corrupt catalog file. One stale .pyc. One bad atom.          ║
║         Sentinel acts on its OWN surface, must report within 60s.        ║
║                                                                           ║
║    R1 — one sentinel's surface                                           ║
║         Cache sentinel's tracked surface. Glyph store. One DB table.    ║
║         Sentinel acts on its surface only, must hold a lease.            ║
║                                                                           ║
║    R2 — Aria software boundary                                           ║
║         sovereign-agent process tree + data_dir + venv.                  ║
║         Conductor authorization REQUIRED. Quorum or operator countermand.║
║                                                                           ║
║    R3 — workstation                                                      ║
║         OS-level state. User account. Filesystem outside data_dir.       ║
║         CANNOT execute autonomously, period. Propose + notify only.      ║
║                                                                           ║
║    R4 — network / server                                                 ║
║         aria-online. Remote endpoints. External services.                ║
║         Same as R3 — request and notify only.                            ║
║                                                                           ║
║    R5 — multi-host / federation                                          ║
║         Out of scope for v0.2.35. Reserved for future federation work. ║
║                                                                           ║
║  The R3+ ceiling is non-negotiable. A local-first agent that can         ║
║  autonomously alter your OS state is no longer local-first. That's the  ║
║  sovereignty line.                                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from enum import IntEnum


class BlastRadius(IntEnum):
    """How far an incident reaches. Higher = bigger blast = less autonomous."""
    R0_ARTIFACT = 0
    R1_SURFACE = 1
    R2_SOFTWARE = 2
    R3_WORKSTATION = 3
    R4_NETWORK = 4
    R5_FEDERATION = 5

    @property
    def label(self) -> str:
        return {
            BlastRadius.R0_ARTIFACT: "R0/artifact",
            BlastRadius.R1_SURFACE: "R1/surface",
            BlastRadius.R2_SOFTWARE: "R2/software",
            BlastRadius.R3_WORKSTATION: "R3/workstation",
            BlastRadius.R4_NETWORK: "R4/network",
            BlastRadius.R5_FEDERATION: "R5/federation",
        }[self]

    @property
    def autonomous_repair_allowed(self) -> bool:
        """True if a Sentinel may execute repair on its own surface without
        a Conductor lease. Only R0 qualifies — and even then the Sentinel
        must report to the Aegis Ledger within 60 seconds."""
        return self == BlastRadius.R0_ARTIFACT

    @property
    def conductor_lease_required(self) -> bool:
        """True if a Conductor-issued lease is required to execute repair.
        R1 and R2 require leases. R3+ cannot be repaired by Aegis at all."""
        return self in (BlastRadius.R1_SURFACE, BlastRadius.R2_SOFTWARE)

    @property
    def operator_only(self) -> bool:
        """True if only the operator can execute repair. Aegis can propose,
        notify, raise DEFCON — but cannot run the repair itself."""
        return self >= BlastRadius.R3_WORKSTATION

    @property
    def quorum_threshold(self) -> int:
        """Minimum corroborating sentinels needed to authorize repair at
        this radius. R0/R1 = 1 (the reporter itself counts).
        R2 = 2 (need a second witness). R3+ = irrelevant — operator decides."""
        if self <= BlastRadius.R1_SURFACE:
            return 1
        if self == BlastRadius.R2_SOFTWARE:
            return 2
        return 0  # not applicable; operator-only


__all__ = ["BlastRadius"]
