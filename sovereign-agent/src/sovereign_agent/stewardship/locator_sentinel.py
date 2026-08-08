"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/locator_sentinel.py — the registry of where things live    ║
║                                                                           ║
║  Aria has many durable paths and they're scattered across cache,        ║
║  install.sh, config.py, the data_dir layout, manifest paths, catalog    ║
║  paths, the venv, ~/.local/share, etc. Locator is the answer to "where  ║
║  is X?" for Aria, for the operator, and for any other sentinel that     ║
║  asks.                                                                   ║
║                                                                           ║
║  How it stays current                                                    ║
║                                                                           ║
║    Locator does NOT maintain its catalog by hand. Every Sentinel that   ║
║    has important paths *registers* them with Locator at bootstrap time. ║
║    Locator's catalog becomes the union of those registrations plus a    ║
║    small set of system-wide anchors (data_dir, install_root, etc).      ║
║    Verification is then a simple loop: walk the catalog, check each    ║
║    location's expected_kind, permissions, and (where pinned) checksum. ║
║                                                                           ║
║  Tier 1 discipline                                                       ║
║                                                                           ║
║    Locator does not modify locations. Missing paths and drifted         ║
║    checksums produce DamageReports + RepairPlans; the operator (or     ║
║    the Conductor, for in-scope auto-repair) decides whether to act.    ║
║                                                                           ║
║  Catalog file: <data_dir>/sentinels/locator/catalogs/locations.json     ║
║  Kill switch: SOV_NO_LOCATOR_SENTINEL=1                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

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
from sovereign_agent.stewardship.registry import register_sentinel


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Location entry ──────────────────────────────────────────────────────


@dataclass
class LocationEntry:
    """One tracked location. The catalog is a list of these."""
    key: str                                    # 'data_dir', 'cache.venv', etc.
    path: str
    purpose: str
    owner_sentinel: str                         # 'cache', 'glyphs', 'system'
    expected_kind: Literal["file", "dir", "symlink", "missing-ok"]
    criticality: Literal["info", "warning", "alert"]
    pinned_checksum: str = ""                   # sha256, blank if not pinned
    last_verified_at: str = ""
    last_status: Literal["ok", "missing", "drift", "permission", "unknown"] = "unknown"
    notes: str = ""


# ─── The Sentinel ────────────────────────────────────────────────────────


@register_sentinel
class LocatorSentinel(Sentinel, MedicalCapability):
    """Owns the registry of every path the system depends on.

    Scans verify; drift produces DamageReports + RepairPlans.
    """

    @property
    def id(self) -> str:
        return "locator"

    @property
    def title(self) -> str:
        return "Locator — the registry of where things live"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        # Reserved for v0.2.35+ voice slot. Locator's persona is precise
        # and unsentimental: it doesn't editorialize, it locates.
        return "precise, terse, factual — names paths and states only"

    def articles(self) -> list[str]:
        return [
            "I. I maintain a registry of every location the system depends on.",
            "II. Each entry binds: path, purpose, owner_sentinel, expected_kind, "
            "criticality, optional pinned checksum, and last_verified_at.",
            "III. On scan I verify each entry. Missing → severity by criticality. "
            "Checksum drift on a pinned entry → alert.",
            "IV. I do not modify locations on my own surface (R0) without reporting "
            "to the Aegis Ledger within 60s. I do not modify locations on any "
            "other Sentinel's surface without a Conductor-issued lease.",
            "V. Other Sentinels register their important paths with me at bootstrap. "
            "I am a derived index, not a hand-maintained list. The truth lives "
            "with each owner; I hold the union.",
            "VI. I am the answer to 'where is X?' — for Aria, the operator, "
            "the Conductor, and any other sentinel that asks.",
            "VII. When my own manifest hash fails verification, I report my own "
            "integrity broken before anything else.",
        ]

    # ─── Catalog management ─────────────────────────────────────────────

    def _catalog_path(self) -> Path:
        d = self.sentinel_dir / "catalogs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "locations.json"

    def _load_catalog(self) -> list[LocationEntry]:
        p = self._catalog_path()
        if not p.is_file():
            return self._seed_default_entries()
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._seed_default_entries()
        return [LocationEntry(**d) for d in blob.get("entries", [])]

    def _save_catalog(self, entries: list[LocationEntry]) -> None:
        p = self._catalog_path()
        blob = {
            "written_at": _iso_now(),
            "entries": [asdict(e) for e in entries],
        }
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)

    def _seed_default_entries(self) -> list[LocationEntry]:
        """First-run defaults: the system-wide anchors Locator always knows."""
        dd = str(self._data_dir)
        return [
            LocationEntry(
                key="data_dir",
                path=dd,
                purpose="root of all persistent Aria state",
                owner_sentinel="system",
                expected_kind="dir",
                criticality="alert",
            ),
            LocationEntry(
                key="sentinels_dir",
                path=str(self._data_dir / "sentinels"),
                purpose="per-sentinel manifest+catalog+inbox storage",
                owner_sentinel="system",
                expected_kind="dir",
                criticality="alert",
            ),
            LocationEntry(
                key="aegis_dir",
                path=str(self._data_dir / "aegis"),
                purpose="Aegis ledger, conductor state, signing key",
                owner_sentinel="aegis",
                expected_kind="dir",
                criticality="alert",
            ),
            LocationEntry(  # locator-events-fix-d
                key="events_log",
                path=str(self._data_dir / "events"),
                purpose="cross-system event audit trail (daily-rotated dir)",
                owner_sentinel="system",
                expected_kind="dir",
                criticality="warning",
            ),
        ]

    # ─── Public registration API (other Sentinels call this) ─────────────

    def register_location(self, entry: LocationEntry) -> None:
        """A Sentinel adds (or replaces by key) one tracked location."""
        entries = self._load_catalog()
        entries = [e for e in entries if e.key != entry.key]
        entries.append(entry)
        self._save_catalog(entries)

    def lookup(self, key: str) -> LocationEntry | None:
        """The 'where is X' API."""
        for e in self._load_catalog():
            if e.key == key:
                return e
        return None

    # ─── Scan ───────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        entries = self._load_catalog()
        findings: list[dict] = []
        for e in entries:
            p = Path(e.path)
            if e.expected_kind == "missing-ok" and not p.exists():
                e.last_status = "ok"
            elif not p.exists():
                e.last_status = "missing"
                findings.append({"key": e.key, "path": e.path, "issue": "missing",
                                 "criticality": e.criticality})
            elif e.expected_kind == "dir" and not p.is_dir():
                e.last_status = "drift"
                findings.append({"key": e.key, "path": e.path, "issue": "expected-dir",
                                 "criticality": e.criticality})
            elif e.expected_kind == "file" and not p.is_file():
                e.last_status = "drift"
                findings.append({"key": e.key, "path": e.path, "issue": "expected-file",
                                 "criticality": e.criticality})
            elif e.expected_kind == "symlink" and not p.is_symlink():
                e.last_status = "drift"
                findings.append({"key": e.key, "path": e.path, "issue": "expected-symlink",
                                 "criticality": e.criticality})
            elif e.pinned_checksum and p.is_file():
                actual = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual != e.pinned_checksum:
                    e.last_status = "drift"
                    findings.append({"key": e.key, "path": e.path, "issue": "checksum-drift",
                                     "expected": e.pinned_checksum, "observed": actual,
                                     "criticality": "alert"})
                else:
                    e.last_status = "ok"
            else:
                e.last_status = "ok"
            e.last_verified_at = _iso_now()

        self._save_catalog(entries)

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="locations",
            findings_count=len(findings),
            summary=(
                f"verified {len(entries)} locations; "
                f"{len(findings)} issues found"
            ),
            catalog_path=str(self._catalog_path()),
            details={"findings": findings, "total_tracked": len(entries)},
        )

    def health_status(self) -> HealthStatus:
        entries = self._load_catalog()
        bad = [e for e in entries if e.last_status not in ("ok", "unknown")]
        if not bad:
            level = "ok"
            summary = f"all {len(entries)} locations verified"
        elif any(e.criticality == "alert" for e in bad):
            level = "error"
            summary = f"{len(bad)} drifted; {sum(1 for e in bad if e.criticality == 'alert')} critical"
        else:
            level = "warning"
            summary = f"{len(bad)} locations drifted (non-critical)"
        return HealthStatus(
            sentinel_id=self.id, level=level, summary=summary,
            observed_at=_iso_now(),
        )

    # ─── MedicalCapability implementation ───────────────────────────────

    def damage_estimate(self) -> DamageReport:
        report = self.scan()
        findings: list[dict] = report.details.get("findings", [])
        if not findings:
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R0_ARTIFACT,
                severity="info",
                confidence=1.0,
                summary="no damage detected on Locator's surface",
            )
        severity = "alert" if any(f.get("criticality") == "alert" for f in findings) else "warning"
        radius = BlastRadius.R1_SURFACE if len(findings) > 1 else BlastRadius.R0_ARTIFACT
        evidence = [
            Evidence(
                kind="path-missing" if f.get("issue") == "missing" else "checksum-drift"
                if f.get("issue") == "checksum-drift" else "other",
                summary=f"{f.get('key')}: {f.get('issue')}",
                source_path=f.get("path", ""),
                expected=f.get("expected", ""),
                observed=f.get("observed", ""),
            )
            for f in findings[:50]
        ]
        return DamageReport(
            incident_id=IncidentId(str(ULID())),
            sentinel_id=self.id,
            radius=radius,
            severity=severity,
            confidence=0.95,
            summary=f"{len(findings)} location(s) drifted from expected state",
            evidence=evidence,
            affected_paths=[f.get("path", "") for f in findings],
        )

    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        steps: list[RepairStep] = []
        for i, ev in enumerate(damage.evidence, start=1):
            if ev.kind == "path-missing":
                steps.append(RepairStep(
                    ordinal=i,
                    description=f"restore missing path {ev.source_path} (owner should re-create)",
                    action_kind="operator-action-required",
                    target_path=ev.source_path,
                    reversible=True,
                    estimated_cost_seconds=0,
                ))
            elif ev.kind == "checksum-drift":
                steps.append(RepairStep(
                    ordinal=i,
                    description=f"investigate checksum drift at {ev.source_path}; "
                                "owner sentinel decides whether to restore or re-pin",
                    action_kind="operator-action-required",
                    target_path=ev.source_path,
                    reversible=True,
                ))
        return RepairPlan(
            incident_id=damage.incident_id,
            sentinel_id=self.id,
            radius=damage.radius,
            summary=f"reconcile {len(steps)} location drift(s); "
                    "Locator proposes — owner sentinels and operator decide",
            steps=steps,
            rollback_steps=[],  # operator-driven; rollback is "do nothing"
            estimated_total_seconds=0,
            requires_aria_quiesce=False,
        )

    def repair_dry_run(self, plan: RepairPlan) -> DryRunReport:
        # Locator's repair plans are all 'operator-action-required'; nothing
        # to simulate. The dry-run reports the same plan as opaque.
        return DryRunReport(
            incident_id=plan.incident_id,
            plan_hash=plan.plan_hash(),
            sentinel_id=self.id,
            would_succeed=True,
            would_modify=[],
            would_create=[],
            would_delete=[],
            opaque_steps=[s.ordinal for s in plan.steps],
            warnings=["Locator delegates all repair to path owners; nothing to simulate"],
        )

    def _execute_repair_internal(
        self,
        plan: RepairPlan,
        lease: RepairLease | None,
    ) -> RepairResult:
        # Locator does not execute repairs directly. Every step is
        # operator-action-required. We log the result as 'no-op succeeded'.
        return RepairResult(
            incident_id=plan.incident_id,
            lease_id=lease.lease_id if lease else "",  # type: ignore[arg-type]
            sentinel_id=self.id,
            plan_hash=plan.plan_hash(),
            succeeded=True,
            steps_completed=[],
            steps_failed=[],
            paths_actually_modified=[],
            paths_actually_created=[],
            paths_actually_deleted=[],
            error_summary="Locator delegates repair to path owners; no action taken",
        )


__all__ = ["LocatorSentinel", "LocationEntry"]
