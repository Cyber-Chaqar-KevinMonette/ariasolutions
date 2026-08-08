"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/medical.py — the MedicalCapability mixin                         ║
║                                                                           ║
║  Every concrete Sentinel composes this in. It exposes the four medic    ║
║  primitives:                                                              ║
║                                                                           ║
║    damage_estimate()   — read-only, no side effects                     ║
║    repair_plan()       — read-only, no side effects                     ║
║    repair_dry_run(plan)— read-only, no side effects                     ║
║    repair_execute(plan, lease) — SIDE-EFFECTING. Refuses without lease. ║
║                                                                           ║
║  The mixin enforces two doctrines structurally:                          ║
║                                                                           ║
║    1. Mixing in the capability does NOT grant authority to use it at    ║
║       scope > R0. R1+ requires a Conductor-issued lease, validated      ║
║       against the conductor key. The Sentinel's repair_execute()        ║
║       performs this check first — before touching the work.            ║
║                                                                           ║
║    2. The check is local, free, and constant-time (hmac.compare_digest).║
║       There is no excuse to skip it. A test that monkeypatches around   ║
║       it is a test bug, not a feature.                                  ║
║                                                                           ║
║  Quiesce protocol:                                                       ║
║                                                                           ║
║    Sentinels track a _quiesced flag. When set, the Sentinel still       ║
║    SCANs (observation is always allowed) but refuses any write or       ║
║    repair. The Conductor sets this on neighbor sentinels during an     ║
║    active R1+ repair so two sentinels don't trip over each other.      ║
║                                                                           ║
║  Why mixin and not subclass:                                             ║
║                                                                           ║
║    A WorkflowSentinel needs to also be a Sentinel. Python's MRO         ║
║    handles cooperative multiple inheritance cleanly when one parent is  ║
║    a mixin with no own state-initialization requirements. Subclassing  ║
║    would force a deep tree (Sentinel→MedicalSentinel→WorkflowSentinel) ║
║    that's harder to evolve.                                             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Optional

from .incidents import (
    DamageReport,
    DryRunReport,
    RepairPlan,
    RepairResult,
)
from .leases import LeaseRefused, RepairLease, verify_lease
from .radius import BlastRadius


class MedicalRefusal(Exception):
    """Raised when MedicalCapability refuses to act for any of these reasons:
    - missing lease
    - lease signature invalid
    - lease expired
    - lease scope doesn't cover this sentinel + plan
    - sentinel is quiesced
    - plan_hash doesn't match the supplied plan
    """


class MedicalCapability:
    """Mixin: gives a Sentinel the four medic primitives.

    Subclasses MUST implement damage_estimate / repair_plan /
    repair_dry_run / _execute_repair_internal. The execute path goes
    through repair_execute(), which validates the lease BEFORE calling
    _execute_repair_internal().
    """

    # ─── State that the mixin manages ───────────────────────────────────
    # These are intentionally underscore-prefixed; the Conductor flips them.
    _quiesced: bool = False
    _conductor_key: Optional[bytes] = None     # set by the Conductor on registration

    # ─── Required abstract methods ──────────────────────────────────────

    @abstractmethod
    def damage_estimate(self) -> DamageReport:
        """Scan-but-don't-act. What's broken on my surface? Read-only."""

    @abstractmethod
    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        """Given a damage report, produce a plan. No side effects."""

    @abstractmethod
    def repair_dry_run(self, plan: RepairPlan) -> DryRunReport:
        """Simulate the plan. Report what WOULD change. No side effects.

        Steps that can't be cleanly dry-run (e.g., a `pip install`) get
        listed in opaque_steps rather than fabricated.
        """

    @abstractmethod
    def _execute_repair_internal(
        self,
        plan: RepairPlan,
        lease: RepairLease,
    ) -> RepairResult:
        """The actual side-effecting work. ONLY called after repair_execute
        has validated the lease. Subclasses implement; callers must not.
        """

    # ─── Public execution surface (with the guard rail) ─────────────────

    def repair_execute(
        self,
        plan: RepairPlan,
        lease: Optional[RepairLease],
    ) -> RepairResult:
        """The ONE public entrypoint to execute repair.

        Validates the lease — signature, scope, target, expiry, and the
        plan_hash binding — BEFORE delegating to _execute_repair_internal.

        For R0 (single artifact) on this Sentinel's own surface, no
        lease is required. The Sentinel must still report to the Aegis
        Ledger within 60s — but that's the Conductor's enforcement, not
        the mixin's. The mixin only enforces what's locally checkable.
        """
        if self._quiesced:
            raise MedicalRefusal(
                f"sentinel {self._sentinel_id()} is quiesced; repair refused"
            )

        if plan.radius == BlastRadius.R0_ARTIFACT and plan.sentinel_id == self._sentinel_id():
            # R0 autonomy: bypass lease, but still verify plan ownership
            return self._execute_repair_internal(plan, lease)  # lease may be None

        if plan.radius >= BlastRadius.R3_WORKSTATION:
            raise MedicalRefusal(
                f"radius {plan.radius.label} is operator-only; Aegis cannot execute"
            )

        if lease is None:
            raise MedicalRefusal("repair at R1+ requires a Conductor-issued lease")

        if self._conductor_key is None:
            raise MedicalRefusal(
                "this Sentinel has not been registered with a Conductor; "
                "no key available to verify lease"
            )

        if not verify_lease(lease, key=self._conductor_key):
            raise MedicalRefusal("lease signature invalid — refusing repair")

        if lease.is_expired():
            raise MedicalRefusal(
                f"lease {lease.lease_id} expired at {lease.expires_at}"
            )

        if not lease.covers(
            sentinel_id=self._sentinel_id(),
            plan_hash=plan.plan_hash(),
        ):
            raise MedicalRefusal(
                f"lease {lease.lease_id} does not cover this "
                f"(sentinel={self._sentinel_id()}, plan_hash={plan.plan_hash()})"
            )

        if lease.scope < plan.radius:
            raise MedicalRefusal(
                f"lease scope {lease.scope.label} below plan radius {plan.radius.label}"
            )

        # All checks passed.
        return self._execute_repair_internal(plan, lease)

    # ─── Quiesce / un-quiesce — Conductor-driven ────────────────────────

    def quiesce(self) -> None:
        """Enter read-only mode. Subsequent repair_execute calls refuse.
        scan() and damage_estimate() remain available — observation is
        always allowed.
        """
        self._quiesced = True

    def unquiesce(self) -> None:
        """Exit read-only mode. Called by Conductor when a neighbor's
        repair lease has been released."""
        self._quiesced = False

    @property
    def is_quiesced(self) -> bool:
        return self._quiesced

    # ─── Registration hook (called by Conductor) ────────────────────────

    def register_with_conductor(self, conductor_key: bytes) -> None:
        """Conductor calls this on every Sentinel at bootstrap, supplying
        the key needed to verify leases. A Sentinel with no key set will
        refuse all R1+ repairs by default — fail-safe.
        """
        self._conductor_key = conductor_key

    # ─── Helper: subclasses must expose their id ─────────────────────────

    def _sentinel_id(self) -> str:
        """Returns the Sentinel's id. Concrete Sentinels already have a
        `.id` property; we look it up dynamically so the mixin doesn't
        require a specific MRO ordering.
        """
        return getattr(self, "id", "<unknown-sentinel>")


__all__ = [
    "MedicalCapability",
    "MedicalRefusal",
]
