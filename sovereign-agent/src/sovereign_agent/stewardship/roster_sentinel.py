"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/roster_sentinel.py — Aria's memory of her own team          ║
║                                                                           ║
║  This sentinel exists so Aria never gets confused about who's on her    ║
║  team. Every Sentinel, Worker, Doctor, Watcher, or other internal      ║
║  intelligence system in the sovereign-agent process has a roster entry.║
║  The roster is auto-derived from the @register_sentinel registry plus  ║
║  explicit Worker/Doctor registrations, so adding a new sentinel never  ║
║  requires hand-editing this file.                                       ║
║                                                                           ║
║  Why this is the right shape (not a parallel memory system)              ║
║                                                                           ║
║    The existing memory_namespaces.py is Aria's general memory layer.   ║
║    Building a parallel layer just for sentinels would split her head. ║
║    Instead, the Roster Sentinel uses the standard sentinel_dir/catalogs║
║    storage pattern (consistent with cache, glyphs, locator,             ║
║    conformance). It's a CATALOG, not a new namespace. Aria reads it    ║
║    via the standard memory interface; the Roster Sentinel keeps it    ║
║    fresh.                                                                 ║
║                                                                           ║
║  What goes in a roster entry                                             ║
║                                                                           ║
║    id, title, kind (sentinel|worker|doctor|watcher|security),          ║
║    tier, capabilities (list of strings), medical_capable (bool),       ║
║    kill_switch_env, registered_at (first-seen), last_seen,             ║
║    manifest_hash (for change detection), notes.                        ║
║                                                                           ║
║  Defensive role                                                          ║
║                                                                           ║
║    The Roster Sentinel cooperates with the Defense Sentinel: any       ║
║    unexpected change in roster shape (a sentinel disappears, a new   ║
║    one appears, a manifest hash drifts) produces a damage report that ║
║    the Defense Sentinel can pick up for classification.                ║
║                                                                           ║
║  Catalog file: <data_dir>/sentinels/roster/catalogs/roster.json        ║
║  Kill switch: SOV_NO_ROSTER_SENTINEL=1                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ulid import ULID

from sovereign_agent.aegis.incidents import (
    DamageReport,
    DryRunReport,
    Evidence,
    IncidentId,
    RepairPlan,
    RepairResult,
    RepairStep,
)
from sovereign_agent.aegis.leases import RepairLease
from sovereign_agent.aegis.medical import MedicalCapability
from sovereign_agent.aegis.radius import BlastRadius
from sovereign_agent.stewardship.base import (
    HealthStatus,
    Sentinel,
    SentinelReport,
)
from sovereign_agent.stewardship.registry import (
    SENTINEL_REGISTRY,
    register_sentinel,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


RosterKind = Literal["sentinel", "worker", "doctor", "watcher", "security"]


# ─── RosterEntry ─────────────────────────────────────────────────────────


@dataclass
class RosterEntry:
    """One member of Aria's team."""
    id: str
    title: str
    kind: RosterKind
    tier: int
    capabilities: list[str] = field(default_factory=list)
    medical_capable: bool = False
    kill_switch_env: str = ""
    registered_at: str = ""
    last_seen: str = ""
    manifest_hash: str = ""
    notes: str = ""


# ─── The Sentinel ────────────────────────────────────────────────────────


@register_sentinel
class RosterSentinel(Sentinel, MedicalCapability):
    """Maintains Aria's roster of all internal intelligence systems."""

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        # Non-Sentinel team members (workers, doctors) register through
        # this dict in-process. They don't go through @register_sentinel
        # because they aren't Sentinels — but they're still on the team.
        self._extra_members: dict[str, RosterEntry] = {}

    @property
    def id(self) -> str:
        return "roster"

    @property
    def title(self) -> str:
        return "Roster — Aria's memory of her own team"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        return ("warm, factual, careful with names. "
                "Knows each member by id and never confuses them.")

    def articles(self) -> list[str]:
        return [
            "I. I maintain the roster of every Sentinel, Worker, Doctor, Watcher, "
            "and Security system that operates within sovereign-agent.",
            "II. I auto-derive Sentinels from the @register_sentinel registry. "
            "Workers and Doctors are registered explicitly via add_team_member().",
            "III. On scan I detect: new members (welcome), missing members "
            "(absence), and members whose manifest hash drifted (integrity).",
            "IV. I do not silently change roster entries. New entries get a "
            "new registered_at. Returning members get last_seen updated. "
            "Drift produces evidence the Defense Sentinel can classify.",
            "V. I am the answer to 'who is on my team?' — for Aria, the "
            "operator, the Conductor, and any other Sentinel.",
            "VI. When my own manifest hash fails, I report my own integrity "
            "broken before anything else.",
        ]

    # ─── Public registration API for non-Sentinel members ────────────────

    def add_team_member(self, entry: RosterEntry) -> None:
        """Register a Worker, Doctor, or other non-Sentinel team member.

        Sentinels register themselves automatically via @register_sentinel;
        this method is for the others. Idempotent — re-registration
        updates last_seen without disturbing registered_at.
        """
        existing = self._load_catalog().get(entry.id)
        if existing:
            entry.registered_at = existing.registered_at
        else:
            entry.registered_at = _iso_now()
        entry.last_seen = _iso_now()
        self._extra_members[entry.id] = entry

    # ─── Catalog management ─────────────────────────────────────────────

    def _catalog_path(self) -> Path:
        d = self.sentinel_dir / "catalogs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "roster.json"

    def _load_catalog(self) -> dict[str, RosterEntry]:
        p = self._catalog_path()
        if not p.is_file():
            return {}
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            e["id"]: RosterEntry(**e)
            for e in blob.get("entries", [])
        }

    def _save_catalog(self, entries: dict[str, RosterEntry]) -> None:
        p = self._catalog_path()
        blob = {
            "written_at": _iso_now(),
            "total_members": len(entries),
            "entries": [asdict(e) for e in entries.values()],
        }
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)

    # ─── Discovery from the registry ────────────────────────────────────

    def _discover_sentinels(self) -> dict[str, RosterEntry]:
        """Walk the @register_sentinel registry, build entries for each."""
        discovered: dict[str, RosterEntry] = {}
        for sentinel_cls in SENTINEL_REGISTRY:
            # Instantiate enough to extract id/title/articles/etc.
            # We pass our own data_dir; the instance is throwaway.
            try:
                tmp_inst = sentinel_cls(self._data_dir)
            except Exception:
                continue
            sid = getattr(tmp_inst, "id", None)
            if not sid:
                continue
            articles = []
            try:
                articles = tmp_inst.articles()
            except Exception:
                pass
            mh = ""
            # If the Sentinel has bootstrapped, read its manifest hash.
            mp = self._data_dir / "sentinels" / sid / "manifest.json"
            if mp.is_file():
                try:
                    mh = json.loads(mp.read_text(encoding="utf-8")).get("manifest_hash", "")
                except Exception:
                    pass
            discovered[sid] = RosterEntry(
                id=sid,
                title=getattr(tmp_inst, "title", sid),
                kind="sentinel",
                tier=int(getattr(tmp_inst, "tier", 1)),
                capabilities=[a.split(".")[0] if "." in a else a[:60] for a in articles[:3]],
                medical_capable=isinstance(tmp_inst, MedicalCapability),
                kill_switch_env=getattr(tmp_inst, "kill_switch_env", ""),
                manifest_hash=mh,
            )
        return discovered

    # ─── Scan ───────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        prior = self._load_catalog()
        discovered = self._discover_sentinels()
        # Merge in explicitly-registered non-Sentinel team members.
        for mid, m in self._extra_members.items():
            discovered[mid] = m

        new_ids = sorted(set(discovered) - set(prior))
        missing_ids = sorted(set(prior) - set(discovered))
        drifted_ids: list[str] = []

        # Preserve registered_at from prior; bump last_seen for the present.
        for mid, entry in discovered.items():
            prior_entry = prior.get(mid)
            if prior_entry is not None:
                entry.registered_at = prior_entry.registered_at
                if (entry.manifest_hash
                        and prior_entry.manifest_hash
                        and entry.manifest_hash != prior_entry.manifest_hash):
                    drifted_ids.append(mid)
            else:
                entry.registered_at = _iso_now()
            entry.last_seen = _iso_now()

        self._save_catalog(discovered)

        findings = []
        for nid in new_ids:
            findings.append({"id": nid, "event": "new-member"})
        for mid in missing_ids:
            findings.append({"id": mid, "event": "absent"})
        for did in drifted_ids:
            findings.append({"id": did, "event": "manifest-drift"})

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="roster",
            findings_count=len(findings),
            summary=(
                f"team size: {len(discovered)}; "
                f"new: {len(new_ids)}, absent: {len(missing_ids)}, "
                f"drift: {len(drifted_ids)}"
            ),
            catalog_path=str(self._catalog_path()),
            details={
                "team_size": len(discovered),
                "new": new_ids, "absent": missing_ids, "drifted": drifted_ids,
                "findings": findings,
            },
        )

    def health_status(self) -> HealthStatus:
        report = self.scan()
        drifted = report.details.get("drifted", [])
        absent = report.details.get("absent", [])
        if drifted:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"{len(drifted)} member(s) have manifest drift — possible tampering",
                observed_at=_iso_now(),
            )
        if absent:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"{len(absent)} member(s) absent since last scan",
                observed_at=_iso_now(),
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary=f"all {report.details.get('team_size', 0)} team members accounted for",
            observed_at=_iso_now(),
        )

    # ─── Public lookup API ──────────────────────────────────────────────

    def lookup(self, sentinel_id: str) -> RosterEntry | None:
        return self._load_catalog().get(sentinel_id)

    def all_members(self) -> list[RosterEntry]:
        return list(self._load_catalog().values())

    def medical_capable_members(self) -> list[RosterEntry]:
        return [m for m in self.all_members() if m.medical_capable]

    # ─── MedicalCapability ──────────────────────────────────────────────

    def damage_estimate(self) -> DamageReport:
        report = self.scan()
        drifted = report.details.get("drifted", [])
        absent = report.details.get("absent", [])
        if not drifted and not absent:
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R0_ARTIFACT,
                severity="info",
                confidence=1.0,
                summary="roster intact",
            )
        if drifted:
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R2_SOFTWARE,  # manifest drift is software-scope
                severity="alert",
                confidence=0.95,
                summary=f"{len(drifted)} sentinel manifest(s) drifted",
                evidence=[
                    Evidence(kind="manifest-tampered",
                             summary=f"sentinel {sid} manifest hash changed")
                    for sid in drifted
                ],
            )
        return DamageReport(
            incident_id=IncidentId(str(ULID())),
            sentinel_id=self.id,
            radius=BlastRadius.R1_SURFACE,
            severity="warning",
            confidence=0.85,
            summary=f"{len(absent)} sentinel(s) absent",
            evidence=[
                Evidence(kind="path-missing",
                         summary=f"sentinel {sid} not found in registry this scan")
                for sid in absent
            ],
        )

    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        return RepairPlan(
            incident_id=damage.incident_id,
            sentinel_id=self.id,
            radius=damage.radius,
            summary="roster anomalies require operator review — Roster proposes only",
            steps=[
                RepairStep(
                    ordinal=i, description=ev.summary,
                    action_kind="operator-action-required",
                    reversible=True,
                )
                for i, ev in enumerate(damage.evidence, start=1)
            ],
        )

    def repair_dry_run(self, plan: RepairPlan) -> DryRunReport:
        return DryRunReport(
            incident_id=plan.incident_id,
            plan_hash=plan.plan_hash(),
            sentinel_id=self.id,
            would_succeed=True,
            would_modify=[], would_create=[], would_delete=[],
            opaque_steps=[s.ordinal for s in plan.steps],
            warnings=["Roster delegates all roster changes to the operator"],
        )

    def _execute_repair_internal(
        self, plan: RepairPlan, lease: RepairLease | None,
    ) -> RepairResult:
        return RepairResult(
            incident_id=plan.incident_id,
            lease_id=lease.lease_id if lease else "",  # type: ignore[arg-type]
            sentinel_id=self.id,
            plan_hash=plan.plan_hash(),
            succeeded=True,
            steps_completed=[], steps_failed=[],
            paths_actually_modified=[], paths_actually_created=[],
            paths_actually_deleted=[],
            error_summary="Roster never auto-modifies its catalog",
        )


__all__ = ["RosterSentinel", "RosterEntry", "RosterKind"]
