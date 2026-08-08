"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/conductor.py — the incident response orchestrator                  ║
║                                                                           ║
║  Singleton. The ONLY module in Aria whose articles say "I am authorized ║
║  to direct other sentinels." Every other Sentinel's articles say        ║
║  "I propose, the Conductor (or operator) decides."                       ║
║                                                                           ║
║  Responsibilities:                                                       ║
║                                                                           ║
║    • Receive lockdown / damage requests from Sentinels                  ║
║    • Apply blast-radius classification and quorum rules                 ║
║    • Issue (and revoke) signed RepairLeases                             ║
║    • Maintain DEFCON state and gate transitions                         ║
║    • Quiesce / unquiesce neighbor Sentinels during active repairs       ║
║    • Maintain the dead-man's switch:                                    ║
║         - persist state after every transition                          ║
║         - rotate writer token on BLACK entry                            ║
║         - on crash-restart, resume from last persisted state            ║
║                                                                           ║
║  What the Conductor explicitly does NOT do:                              ║
║                                                                           ║
║    • Decide repairs at R3+ — those are operator-only                    ║
║    • Override a kill switch — SOV_NO_AEGIS or per-sentinel switches    ║
║      always win                                                          ║
║    • Persist anything user-facing — that's the operator-visible         ║
║      notification channel's job; the Conductor writes structured        ║
║      records to the Aegis Ledger only                                   ║
║    • Apologize for being conservative — when quorum isn't met or        ║
║      classification is uncertain, the Conductor escalates to the        ║
║      operator. False positives on caution are not bugs.                ║
║                                                                           ║
║  Crash-only software discipline (Candea & Fox, 2003):                  ║
║                                                                           ║
║    The Conductor doesn't *recover* from crashes. It just *restarts     ║
║    cleanly from the last persisted state.* Every state-affecting        ║
║    operation:                                                            ║
║                                                                           ║
║      1. Compute the new state                                            ║
║      2. Persist it to disk (state.json under aegis/)                    ║
║      3. Write the ledger entry                                          ║
║      4. Apply the in-memory change                                      ║
║                                                                           ║
║    If we crash between (2) and (3), the next bootstrap reconciles by   ║
║    walking the ledger and replaying any unrecorded transitions. If we  ║
║    crash between (3) and (4), no harm — (4) is idempotent on next     ║
║    bootstrap.                                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ulid import ULID

from .defcon import Defcon, DefconTransition, transition_allowed
from .incidents import (
    DamageReport,
    Incident,
    IncidentId,
    LeaseId,
    RepairPlan,
    RepairResult,
)
from .leases import (
    KeyPermissionError,
    RepairLease,
    load_or_create_conductor_key,
    sign_lease,
)
from .ledger import AegisLedger
from .radius import BlastRadius

logger = logging.getLogger(__name__)

MASTER_KILL_SWITCH_ENV = "SOV_NO_AEGIS"

# Lease TTLs by scope. Tighter for bigger blast radius.
LEASE_TTL_SECONDS = {
    BlastRadius.R0_ARTIFACT: 60,
    BlastRadius.R1_SURFACE: 300,       # 5 min
    BlastRadius.R2_SOFTWARE: 900,      # 15 min
}

# Quiet period for YELLOW → GREEN auto-downgrade
QUIET_PERIOD_SECONDS = 600  # 10 min


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── ConductorState (the persisted blob) ──────────────────────────────────


@dataclass
class ConductorState:
    """The Conductor's persisted state. Crash-only software lives here.

    NOT frozen — it mutates. Persisted to <data_dir>/aegis/state.json
    after every transition.
    """
    defcon: Defcon = Defcon.GREEN
    writer_token: str = ""                     # rotated on BLACK entry
    bootstrapped_at: str = ""
    last_transition_at: str = ""
    last_transition_reason: str = ""
    last_yellow_evidence_at: str = ""          # supports quiet-period check
    open_incidents: list[str] = field(default_factory=list)   # IncidentIds
    active_leases: list[str] = field(default_factory=list)    # LeaseIds
    quiesced_sentinels: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        d = {
            "defcon": int(self.defcon),
            "writer_token": self.writer_token,
            "bootstrapped_at": self.bootstrapped_at,
            "last_transition_at": self.last_transition_at,
            "last_transition_reason": self.last_transition_reason,
            "last_yellow_evidence_at": self.last_yellow_evidence_at,
            "open_incidents": self.open_incidents,
            "active_leases": self.active_leases,
            "quiesced_sentinels": self.quiesced_sentinels,
        }
        return json.dumps(d, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, blob: str) -> "ConductorState":
        d = json.loads(blob)
        return cls(
            defcon=Defcon(d.get("defcon", 0)),
            writer_token=d.get("writer_token", ""),
            bootstrapped_at=d.get("bootstrapped_at", ""),
            last_transition_at=d.get("last_transition_at", ""),
            last_transition_reason=d.get("last_transition_reason", ""),
            last_yellow_evidence_at=d.get("last_yellow_evidence_at", ""),
            open_incidents=list(d.get("open_incidents", [])),
            active_leases=list(d.get("active_leases", [])),
            quiesced_sentinels=list(d.get("quiesced_sentinels", [])),
        )


# ─── AegisConductor ──────────────────────────────────────────────────────


class AegisConductor:
    """The orchestrator. Construct once per process.

    Lifecycle:
      conductor = AegisConductor(data_dir)
      conductor.bootstrap()              # idempotent — loads state, key, ledger
      conductor.register_sentinel(s)     # for each MedicalCapability-equipped sentinel
      ...
      report = conductor.intake(damage_report)
      lease = conductor.request_lease(plan)
      conductor.release_lease(lease)
      conductor.report_repair_result(result)
      ...
      conductor.shutdown()
    """

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._aegis_dir = data_dir / "aegis"
        self._state_path = self._aegis_dir / "state.json"
        self._state = ConductorState()
        self._key: Optional[bytes] = None
        self._ledger: Optional[AegisLedger] = None
        self._bootstrapped = False

        # In-memory incident store. Lost on crash; reconstructed by replaying
        # the ledger on next bootstrap.
        self._incidents: dict[IncidentId, Incident] = {}
        self._leases: dict[LeaseId, RepairLease] = {}

        # Registered Sentinels (MedicalCapability-equipped). Keyed by id.
        # The Conductor uses these to quiesce/unquiesce neighbors.
        self._sentinels: dict[str, object] = {}

    # ─── Disabled-mode check ────────────────────────────────────────────

    @property
    def is_disabled(self) -> bool:
        """True if SOV_NO_AEGIS=1 is set. Disabled Conductor refuses all
        operations except shutdown(); system reverts to v0.2.34 behavior.
        """
        return bool(os.environ.get(MASTER_KILL_SWITCH_ENV))

    # ─── Bootstrap ──────────────────────────────────────────────────────

    def bootstrap(self) -> None:
        """Initialize. Idempotent. Safe to call after a crash-restart.

        Steps:
          1. Verify (or create + lock down) the conductor signing key.
          2. Open the Aegis Ledger.
          3. Load persisted state if present, else initialize fresh.
          4. Walk the ledger to reconcile in-memory incident view.
          5. Rotate the writer_token on every bootstrap (defends against
             stale tokens after crash-restart).
          6. Write a 'conductor-bootstrap' ledger entry.
        """
        if self.is_disabled:
            logger.info("Aegis Conductor disabled via %s", MASTER_KILL_SWITCH_ENV)
            return

        self._aegis_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        try:
            self._key = load_or_create_conductor_key(self._data_dir)
        except KeyPermissionError as e:
            logger.error("Aegis bootstrap aborted: %s", e)
            raise

        self._ledger = AegisLedger(self._data_dir)

        if self._state_path.is_file():
            try:
                self._state = ConductorState.from_json(
                    self._state_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Aegis state file unreadable; starting from clean GREEN. "
                    "Ledger will be replayed to reconstruct incident view."
                )
                self._state = ConductorState()

        if not self._state.bootstrapped_at:
            self._state.bootstrapped_at = _iso_now()

        # Always rotate the writer token on bootstrap.
        self._state.writer_token = secrets.token_hex(16)

        self._persist_state()

        self._ledger.append(
            kind="conductor-bootstrap",
            actor="conductor",
            data={
                "defcon_at_bootstrap": int(self._state.defcon),
                "open_incidents_carried_over": len(self._state.open_incidents),
            },
            conductor_token=self._state.writer_token,
        )

        self._bootstrapped = True

    def shutdown(self) -> None:
        if not self._bootstrapped or self._ledger is None:
            return
        try:
            self._ledger.append(
                kind="conductor-shutdown",
                actor="conductor",
                data={"defcon": int(self._state.defcon)},
                conductor_token=self._state.writer_token,
            )
        except Exception:
            pass

    # ─── Sentinel registration ─────────────────────────────────────────

    def register_sentinel(self, sentinel: object) -> None:
        """Wire a MedicalCapability-equipped Sentinel into the Conductor.

        The Sentinel receives the conductor key so it can verify leases.
        Without this call, the Sentinel refuses all R1+ repair attempts
        (the MedicalCapability mixin's fail-safe).
        """
        if self.is_disabled or self._key is None:
            return
        sid = getattr(sentinel, "id", None)
        if not sid:
            raise ValueError("register_sentinel: sentinel has no .id")
        register_fn = getattr(sentinel, "register_with_conductor", None)
        if register_fn is None:
            # Not a MedicalCapability-equipped Sentinel; that's fine, the
            # Conductor still tracks it for quiesce purposes but won't
            # issue leases to it.
            self._sentinels[sid] = sentinel
            return
        register_fn(self._key)
        self._sentinels[sid] = sentinel

    # ─── Intake: a Sentinel reports damage ─────────────────────────────

    def intake(self, damage: DamageReport) -> IncidentId:
        """A Sentinel hands us a DamageReport. Open or merge into an
        existing incident, log it, possibly elevate DEFCON.

        Returns the IncidentId so the Sentinel can reference it in
        subsequent calls.
        """
        self._require_bootstrapped()
        if self.is_disabled:
            return damage.incident_id

        existing = self._incidents.get(damage.incident_id)
        if existing is None:
            new_incident = Incident(
                incident_id=damage.incident_id,
                radius=damage.radius,
                opened_at=damage.observed_at,
                primary_sentinel_id=damage.sentinel_id,
                severity=damage.severity,
                summary=damage.summary,
                damage_reports=[damage],
            )
            self._incidents[damage.incident_id] = new_incident
            self._state.open_incidents.append(damage.incident_id)
            self._ledger.append(  # type: ignore[union-attr]
                kind="incident-opened",
                actor=damage.sentinel_id,
                data={
                    "incident_id": damage.incident_id,
                    "radius": int(damage.radius),
                    "severity": damage.severity,
                    "summary": damage.summary,
                    "confidence": damage.confidence,
                },
                conductor_token=self._state.writer_token,
            )
        else:
            # Corroboration: same incident, different witness.
            merged = Incident(
                incident_id=existing.incident_id,
                radius=max(existing.radius, damage.radius),
                opened_at=existing.opened_at,
                primary_sentinel_id=existing.primary_sentinel_id,
                severity=existing.severity,  # primary defines severity
                summary=existing.summary,
                damage_reports=list(existing.damage_reports) + [damage],
                proposed_plans=existing.proposed_plans,
                executed_results=existing.executed_results,
                closed_at=existing.closed_at,
                resolution=existing.resolution,
            )
            self._incidents[damage.incident_id] = merged

        self._ledger.append(  # type: ignore[union-attr]
            kind="damage-reported",
            actor=damage.sentinel_id,
            data={
                "incident_id": damage.incident_id,
                "evidence_count": len(damage.evidence),
                "affected_paths": damage.affected_paths[:20],  # cap
                "confidence": damage.confidence,
            },
            conductor_token=self._state.writer_token,
        )

        # Track latest evidence timestamp for YELLOW quiet-period logic.
        self._state.last_yellow_evidence_at = damage.observed_at

        # Possibly elevate DEFCON.
        self._maybe_elevate(damage)
        self._persist_state()
        return damage.incident_id

    # ─── Lease lifecycle ────────────────────────────────────────────────

    def request_lease(self, plan: RepairPlan) -> RepairLease | None:
        """A Sentinel asks for authority to execute a RepairPlan.

        Returns a signed lease, or None if the request is denied.
        Reasons for denial: corroboration insufficient for the radius,
        another lease already covers an overlapping scope, plan refers
        to an unknown incident, sentinel is quiesced, DEFCON is BLACK,
        or radius is operator-only (R3+).
        """
        self._require_bootstrapped()
        if self.is_disabled:
            return None
        if self._state.defcon == Defcon.BLACK:
            logger.info("lease refused: DEFCON BLACK")
            return None
        if plan.radius >= BlastRadius.R3_WORKSTATION:
            return None
        if plan.sentinel_id in self._state.quiesced_sentinels:
            return None

        incident = self._incidents.get(plan.incident_id)
        if incident is None:
            return None

        # Corroboration check.
        if incident.corroboration_count() < plan.radius.quorum_threshold:
            logger.info(
                "lease refused for incident %s: corroboration %d < threshold %d",
                plan.incident_id,
                incident.corroboration_count(),
                plan.radius.quorum_threshold,
            )
            return None

        # Issue lease.
        lease_id = LeaseId(str(ULID()))
        ttl = LEASE_TTL_SECONDS.get(plan.radius, 60)
        assert self._key is not None
        lease = sign_lease(
            lease_id=lease_id,
            incident_id=plan.incident_id,
            sentinel_id=plan.sentinel_id,
            scope=plan.radius,
            plan_hash=plan.plan_hash(),
            ttl_seconds=ttl,
            key=self._key,
        )
        self._leases[lease_id] = lease
        self._state.active_leases.append(lease_id)

        # Quiesce neighbors on the same surface for R1+.
        if plan.radius >= BlastRadius.R1_SURFACE:
            self._quiesce_neighbors(plan.sentinel_id)

        self._ledger.append(  # type: ignore[union-attr]
            kind="lease-issued",
            actor="conductor",
            data={
                "lease_id": lease_id,
                "incident_id": plan.incident_id,
                "sentinel_id": plan.sentinel_id,
                "scope": int(plan.radius),
                "plan_hash": plan.plan_hash(),
                "ttl_seconds": ttl,
            },
            conductor_token=self._state.writer_token,
        )
        self._persist_state()
        return lease

    def release_lease(self, lease_id: LeaseId) -> None:
        """Sentinel signals it's done. Unquiesce neighbors."""
        self._require_bootstrapped()
        if self.is_disabled:
            return
        lease = self._leases.pop(lease_id, None)
        if lease_id in self._state.active_leases:
            self._state.active_leases.remove(lease_id)
        if lease is not None and lease.scope >= BlastRadius.R1_SURFACE:
            self._unquiesce_neighbors(lease.sentinel_id)
        self._persist_state()

    def report_repair_result(self, result: RepairResult) -> None:
        """Sentinel reports the outcome. Log it; release the lease."""
        self._require_bootstrapped()
        if self.is_disabled:
            return
        self._ledger.append(  # type: ignore[union-attr]
            kind="repair-executed",
            actor=result.sentinel_id,
            data={
                "incident_id": result.incident_id,
                "lease_id": result.lease_id,
                "succeeded": result.succeeded,
                "rollback_invoked": result.rollback_invoked,
                "rollback_succeeded": result.rollback_succeeded,
                "steps_completed": result.steps_completed,
                "steps_failed": result.steps_failed,
            },
            conductor_token=self._state.writer_token,
        )
        self.release_lease(result.lease_id)

        # If repair succeeded and no other incidents, consider downgrade.
        if result.succeeded and not self._state.open_incidents:
            self._maybe_downgrade()

    # ─── DEFCON transitions ─────────────────────────────────────────────

    def _maybe_elevate(self, damage: DamageReport) -> None:
        """Possibly raise DEFCON based on incoming damage."""
        target = self._state.defcon
        if damage.severity == "critical" or damage.radius >= BlastRadius.R2_SOFTWARE:
            target = max(target, Defcon.RED)
        elif damage.severity == "alert":
            target = max(target, Defcon.ORANGE)
        elif damage.severity == "warning":
            target = max(target, Defcon.YELLOW)

        # Manifest-tampered evidence from 3+ sentinels → BLACK.
        manifest_tampered_count = 0
        for inc_id in self._state.open_incidents:
            inc = self._incidents.get(IncidentId(inc_id))
            if inc is None:
                continue
            for dr in inc.damage_reports:
                if any(e.kind == "manifest-tampered" for e in dr.evidence):
                    manifest_tampered_count += 1
                    break
        if manifest_tampered_count >= 3:
            target = Defcon.BLACK

        if target != self._state.defcon:
            self._transition(
                target=target,
                reason=f"incident {damage.incident_id} severity={damage.severity} "
                       f"radius={damage.radius.label}",
                triggered_by="conductor",
                incident_id=damage.incident_id,
                operator_authorized=False,
            )

    def _maybe_downgrade(self) -> None:
        """Possibly drop DEFCON one level. Only YELLOW→GREEN is autonomous."""
        if self._state.defcon != Defcon.YELLOW:
            return
        # Quiet-period satisfied? Check elapsed since last yellow evidence.
        if not self._state.last_yellow_evidence_at:
            return
        try:
            last = datetime.strptime(
                self._state.last_yellow_evidence_at, "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        except ValueError:
            return
        if elapsed < QUIET_PERIOD_SECONDS:
            return
        self._transition(
            target=Defcon.GREEN,
            reason=f"YELLOW→GREEN: {elapsed:.0f}s of quiet (threshold {QUIET_PERIOD_SECONDS}s)",
            triggered_by="conductor",
            operator_authorized=False,
            quiet_period_satisfied=True,
        )

    def operator_downgrade(self, target: Defcon, reason: str) -> bool:
        """Operator-initiated downgrade. Returns True if applied."""
        self._require_bootstrapped()
        if self.is_disabled:
            return False
        return self._transition(
            target=target,
            reason=reason,
            triggered_by="operator",
            operator_authorized=True,
        )

    def _transition(
        self,
        *,
        target: Defcon,
        reason: str,
        triggered_by: str,
        incident_id: str = "",
        operator_authorized: bool,
        quiet_period_satisfied: bool = False,
    ) -> bool:
        current = self._state.defcon
        if not transition_allowed(
            current=current,
            target=target,
            operator_authorized=operator_authorized,
            quiet_period_satisfied=quiet_period_satisfied,
        ):
            return False
        if target == current:
            return True

        # Persist BEFORE applying — crash-only software discipline.
        prior_defcon = self._state.defcon
        self._state.defcon = target
        self._state.last_transition_at = _iso_now()
        self._state.last_transition_reason = reason

        # Entering BLACK rotates the writer token — every Sentinel with a
        # stale token now finds its writes refused. They must re-fetch.
        if target == Defcon.BLACK:
            self._state.writer_token = secrets.token_hex(16)

        self._persist_state()
        self._ledger.append(  # type: ignore[union-attr]
            kind="defcon-transition",
            actor=triggered_by,
            data={
                "from": int(prior_defcon),
                "to": int(target),
                "reason": reason,
                "incident_id": incident_id,
            },
            conductor_token=self._state.writer_token,
        )
        return True

    # ─── Quiesce neighbors ──────────────────────────────────────────────

    def _quiesce_neighbors(self, leaseholder_id: str) -> None:
        """Set is_quiesced=True on every other registered Sentinel.

        Coarse-grained for v0.2.35 — we don't yet know which Sentinels
        share a surface with the leaseholder, so we conservatively quiesce
        all of them. Future: per-surface quiesce based on Locator's
        location registry.
        """
        for sid, sentinel in self._sentinels.items():
            if sid == leaseholder_id:
                continue
            quiesce_fn = getattr(sentinel, "quiesce", None)
            if quiesce_fn is None:
                continue
            try:
                quiesce_fn()
                if sid not in self._state.quiesced_sentinels:
                    self._state.quiesced_sentinels.append(sid)
            except Exception:
                pass

    def _unquiesce_neighbors(self, leaseholder_id: str) -> None:
        """Release every quiesced sentinel after a lease ends."""
        for sid in list(self._state.quiesced_sentinels):
            sentinel = self._sentinels.get(sid)
            if sentinel is None:
                continue
            unquiesce_fn = getattr(sentinel, "unquiesce", None)
            if unquiesce_fn is None:
                continue
            try:
                unquiesce_fn()
            except Exception:
                pass
        self._state.quiesced_sentinels.clear()

    # ─── Persistence ────────────────────────────────────────────────────

    def _persist_state(self) -> None:
        """Write state.json atomically (write-then-rename)."""
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(self._state.to_json(), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._state_path)

    # ─── Sanity ─────────────────────────────────────────────────────────

    def _require_bootstrapped(self) -> None:
        if not self._bootstrapped and not self.is_disabled:
            raise RuntimeError("AegisConductor.bootstrap() must be called first")

    # ─── Public introspection ───────────────────────────────────────────

    @property
    def defcon(self) -> Defcon:
        return self._state.defcon

    @property
    def open_incident_count(self) -> int:
        return len(self._state.open_incidents)

    @property
    def active_lease_count(self) -> int:
        return len(self._state.active_leases)


__all__ = [
    "AegisConductor",
    "ConductorState",
    "MASTER_KILL_SWITCH_ENV",
    "LEASE_TTL_SECONDS",
    "QUIET_PERIOD_SECONDS",
]
