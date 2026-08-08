"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/incidents.py — typed records for incident response                ║
║                                                                           ║
║  These dataclasses are the contract between Sentinels and the Conductor. ║
║  Every report, every plan, every dry-run, every result passes through   ║
║  these shapes. They're frozen (immutable) because audit trails are     ║
║  worthless if the records can change after the fact.                    ║
║                                                                           ║
║  The flow:                                                                ║
║                                                                           ║
║    Sentinel detects → DamageReport (read-only)                           ║
║    Sentinel proposes → RepairPlan (read-only, no side effects yet)       ║
║    Anyone curious → DryRunReport (simulates RepairPlan, no side effects) ║
║    Conductor authorizes → RepairLease (in aegis/leases.py)               ║
║    Sentinel executes → RepairResult (the actual outcome)                 ║
║                                                                           ║
║  Evidence is a small union type. We don't try to encode every possible  ║
║  diagnostic shape — just enough that the Conductor can corroborate       ║
║  claims across Sentinels without parsing prose.                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, NewType

from .radius import BlastRadius


IncidentId = NewType("IncidentId", str)   # ULID
LeaseId = NewType("LeaseId", str)         # ULID


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Evidence ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Evidence:
    """One concrete signal supporting (or refuting) an incident claim.

    Frozen on purpose. Evidence shouldn't morph after it's been observed.
    """
    kind: Literal[
        "hash-mismatch",       # a manifest or catalog hash failed verification
        "path-missing",        # an expected path is gone
        "path-permission",     # a path is present but permissions changed
        "threshold-breach",    # a tracked metric crossed an alert threshold
        "rate-anomaly",        # something happening too fast or too slow
        "version-drift",       # version strings disagree across surfaces
        "checksum-drift",      # a pinned file's content changed
        "manifest-tampered",   # a Sentinel's own manifest hash broke
        "process-unresponsive", # subprocess heartbeat missed
        "other",
    ]
    summary: str
    detail: str = ""
    source_path: str = ""
    expected: str = ""
    observed: str = ""
    observed_at: str = field(default_factory=_iso_now)


# ─── DamageReport ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DamageReport:
    """What a Sentinel sees broken on its own surface.

    READ-ONLY. Generating this must not have side effects. Multiple
    Sentinels can independently produce a DamageReport for the same
    underlying issue — that's how the Conductor builds corroboration.
    """
    incident_id: IncidentId
    sentinel_id: str                          # who is reporting
    radius: BlastRadius
    severity: Literal["info", "warning", "alert", "critical"]
    confidence: float                          # 0.0..1.0, calibrated
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    affected_paths: list[str] = field(default_factory=list)
    affected_atoms: list[str] = field(default_factory=list)   # ULIDs
    observed_at: str = field(default_factory=_iso_now)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence out of range [0,1]: {self.confidence}")


# ─── RepairPlan ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RepairStep:
    """One step in a RepairPlan. Ordered. Atomic enough to roll back."""
    ordinal: int
    description: str                           # human-readable
    action_kind: Literal[
        "rebuild-catalog",
        "restore-from-backup",
        "rotate-credential",
        "reinstall-package",
        "drop-stale-cache",
        "rewrite-manifest",
        "quiesce-sentinel",
        "operator-action-required",
        "other",
    ]
    target_path: str = ""
    reversible: bool = True
    estimated_cost_seconds: int = 0
    prerequisites: list[str] = field(default_factory=list)   # ordinals of prior steps


@dataclass(frozen=True)
class RepairPlan:
    """A Sentinel's proposal for fixing a damage.

    READ-ONLY at this stage — emitting a RepairPlan must not have side
    effects. The plan's hash (computed below) ends up baked into the
    RepairLease that authorizes it; if the plan changes, the lease is
    invalid.
    """
    incident_id: IncidentId
    sentinel_id: str                           # who's proposing
    radius: BlastRadius
    summary: str
    steps: list[RepairStep] = field(default_factory=list)
    rollback_steps: list[RepairStep] = field(default_factory=list)
    estimated_total_seconds: int = 0
    requires_aria_quiesce: bool = False        # does Aria's main loop need to yield?
    created_at: str = field(default_factory=_iso_now)

    def plan_hash(self) -> str:
        """Deterministic hash over the plan's content. Lease binds to this."""
        import hashlib
        import json
        from dataclasses import asdict
        blob = json.dumps({
            "incident_id": self.incident_id,
            "sentinel_id": self.sentinel_id,
            "radius": int(self.radius),
            "summary": self.summary,
            "steps": [asdict(s) for s in self.steps],
            "rollback_steps": [asdict(s) for s in self.rollback_steps],
        }, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


# ─── DryRunReport ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DryRunReport:
    """The result of simulating a RepairPlan without executing it.

    A Sentinel produces this so the operator (or the Conductor's policy
    checks) can see what WOULD happen before authorizing. No side effects
    permitted. If a step can't be dry-run cleanly (e.g., 'pip install'
    where the install itself is the simulation), the report says so and
    flags the step as 'opaque' rather than fabricating a simulation.
    """
    incident_id: IncidentId
    plan_hash: str
    sentinel_id: str
    would_succeed: bool                        # best-effort prediction
    would_modify: list[str]                    # paths that would change
    would_create: list[str]                    # paths that would be created
    would_delete: list[str]                    # paths that would be removed
    opaque_steps: list[int]                    # ordinals we couldn't simulate
    warnings: list[str] = field(default_factory=list)
    completed_at: str = field(default_factory=_iso_now)


# ─── RepairResult ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RepairResult:
    """The actual outcome after Sentinel.repair_execute() ran.

    Written to the Aegis Ledger. The lease is referenced by id so the
    audit chain is complete: incident → damage → plan → lease → result.
    """
    incident_id: IncidentId
    lease_id: LeaseId
    sentinel_id: str
    plan_hash: str
    succeeded: bool
    steps_completed: list[int]                 # ordinals
    steps_failed: list[int]
    paths_actually_modified: list[str]
    paths_actually_created: list[str]
    paths_actually_deleted: list[str]
    rollback_invoked: bool = False
    rollback_succeeded: bool = False
    error_summary: str = ""
    completed_at: str = field(default_factory=_iso_now)


# ─── Incident (the top-level record) ──────────────────────────────────────


@dataclass(frozen=True)
class Incident:
    """The aggregate record of an incident from detection to resolution.

    Lives in the Conductor's in-memory state during an active incident,
    and is written to the Aegis Ledger at each state transition. The
    ledger entries are the durable truth; this dataclass is the convenient
    in-process view.
    """
    incident_id: IncidentId
    radius: BlastRadius
    opened_at: str
    primary_sentinel_id: str
    severity: Literal["info", "warning", "alert", "critical"]
    summary: str
    damage_reports: list[DamageReport] = field(default_factory=list)
    proposed_plans: list[RepairPlan] = field(default_factory=list)
    executed_results: list[RepairResult] = field(default_factory=list)
    closed_at: str = ""
    resolution: Literal[
        "open",
        "operator-resolved",
        "auto-resolved",
        "escalated-to-black",
        "rolled-back",
        "abandoned",
    ] = "open"

    def corroboration_count(self) -> int:
        """How many distinct sentinels have witnessed this incident?"""
        return len({r.sentinel_id for r in self.damage_reports})


__all__ = [
    "IncidentId", "LeaseId",
    "Evidence",
    "DamageReport",
    "RepairStep", "RepairPlan",
    "DryRunReport",
    "RepairResult",
    "Incident",
]
