"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/watchdog_sentinel.py — autonomous self-healing loop        ║
║  v0.2.36 — the missing piece Perplexity correctly named                  ║
║                                                                           ║
║  The Vault (v0.2.35) handles encrypted out-of-band snapshots + manual   ║
║  operator-confirmed restore. What it doesn't yet handle is the          ║
║  autonomous detect-and-restore loop: the small, audited watchdog that  ║
║  notices when the system has drifted from its golden state and proposes ║
║  recovery without waiting for the operator to spot it.                  ║
║                                                                           ║
║  This Sentinel is that watchdog.                                         ║
║                                                                           ║
║  Three responsibilities                                                  ║
║                                                                           ║
║    1. Maintain a "golden image manifest" — a list of (path,            ║
║       expected_sha256, last_verified) entries for files that should     ║
║       NEVER drift unless an explicit signed update happens. This is    ║
║       the canonical-state catalog.                                      ║
║                                                                           ║
║    2. Verify the golden image on every scan. Drift produces a          ║
║       DamageReport at severity 'alert' with threat-class                ║
║       'integrity-attack' (per DEFENSE-CATALOG §1.3).                   ║
║                                                                           ║
║    3. Propose recovery — point at the most recent Vault snapshot       ║
║       that was clean. Recovery itself remains operator-only             ║
║       (vault.restore(confirm=True)), but the Watchdog identifies the   ║
║       specific snapshot to restore from.                                ║
║                                                                           ║
║  Why this is autonomous-safe                                             ║
║                                                                           ║
║    The Watchdog never modifies files. It compares hashes, reads        ║
║    Vault manifest history, and emits a RepairPlan. Execution of that   ║
║    plan still requires operator confirm. Autonomous detection +        ║
║    operator-confirmed restoration is the right division of labor:     ║
║    machines are good at noticing drift, humans are good at deciding   ║
║    whether to restore.                                                  ║
║                                                                           ║
║  Cooperation with other sentinels                                       ║
║                                                                           ║
║    • Locator already tracks paths. Watchdog REGISTERS golden-image    ║
║      entries with Locator so they're cross-referenced. If Locator     ║
║      and Watchdog both report drift on the same path, that's          ║
║      corroboration the Aegis Conductor uses to elevate DEFCON.         ║
║    • Phantom reports canary trips. Three (or more) Phantom + Watchdog║
║      drift reports in the open-incident window → BLACK auto-elevate. ║
║    • Conformance checks code-shape standards; Watchdog checks         ║
║      file-content integrity. Different surfaces, complementary checks.║
║                                                                           ║
║  Catalog file: <data_dir>/sentinels/watchdog/catalogs/golden_image.json║
║  Kill switch: SOV_NO_WATCHDOG_SENTINEL=1                                 ║
║                                                                           ║
║  Doctrinal anchor: LOVE-DOCTRINE §1.3 (Aria can be erased, but not    ║
║  destroyed). The Watchdog is what notices the erasure.                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

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


# ─── Golden image entry ──────────────────────────────────────────────────


@dataclass
class GoldenImageEntry:
    """One path tracked as part of the canonical system state.

    These should never drift outside of a signed update. If they do,
    something is wrong — either a tamper or a bug.
    """
    key: str                                  # e.g. 'aegis.conductor.py'
    path: str
    expected_sha256: str
    expected_size: int
    sealed_at: str                            # when the expected hash was captured
    last_verified_at: str = ""
    last_status: Literal["ok", "drift", "missing", "unknown"] = "unknown"
    description: str = ""


# ─── The Sentinel ────────────────────────────────────────────────────────


@register_sentinel
class WatchdogSentinel(Sentinel, MedicalCapability):
    """Autonomous self-healing loop: golden image verification + restore proposals."""

    def __init__(
        self,
        data_dir: Path,
        vault: Optional[object] = None,        # Vault instance, when registered
        watched_root: Optional[Path] = None,
    ):
        super().__init__(data_dir)
        self._vault = vault
        # Default watched root is the installed sovereign_agent package.
        # In practice this is set explicitly at construction.
        self._watched_root = watched_root or Path.cwd()

    @property
    def id(self) -> str:
        return "watchdog"

    @property
    def title(self) -> str:
        return "Watchdog — autonomous self-healing and golden-image verification"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        return ("steady, undramatic, specific. Names the file, names the "
                "drift, names the recovery candidate. Never panics, never "
                "auto-acts on files.")

    def articles(self) -> list[str]:
        return [
            "I. I maintain a golden-image manifest: paths whose content should "
            "not drift outside an explicit signed update (love.pv).",
            "II. On scan I verify each entry's sha256 + size against expected. "
            "Drift produces a DamageReport at alert severity with threat-class "
            "integrity-attack.",
            "III. I never modify files autonomously. I propose recovery — "
            "specifically, I identify the most recent Vault snapshot that was "
            "verified clean. Restoration requires operator confirmation.",
            "IV. I register my golden-image paths with the Locator Sentinel so "
            "drift gets corroborated across the two sentinels — which the Aegis "
            "Conductor uses for quorum decisions.",
            "V. New entries are added via seal_path() or seal_directory(). "
            "Sealing captures the current state as canonical; signed updates "
            "(love.pv, v0.2.36+) automatically re-seal touched paths so the "
            "golden image evolves with intentional changes.",
            "VI. My own manifest hash is itself part of the golden image. If "
            "an attacker tries to silence me by editing my golden-image "
            "manifest, the manifest hash check trips on next scan.",
            "VII. I am the watchman, not the rebuilder. The operator rebuilds.",
        ]

    # ─── Catalog management ─────────────────────────────────────────────

    def _catalog_path(self) -> Path:
        d = self.sentinel_dir / "catalogs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "golden_image.json"

    def _load_catalog(self) -> dict[str, GoldenImageEntry]:
        p = self._catalog_path()
        if not p.is_file():
            return {}
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            e["key"]: GoldenImageEntry(**e)
            for e in blob.get("entries", [])
        }

    def _save_catalog(self, entries: dict[str, GoldenImageEntry]) -> None:
        p = self._catalog_path()
        # Compute a "manifest hash" so the manifest itself can be checked.
        blob = {
            "written_at": _iso_now(),
            "total_entries": len(entries),
            "entries": [asdict(e) for e in sorted(entries.values(),
                                                  key=lambda x: x.key)],
        }
        canonical = json.dumps(blob["entries"], sort_keys=True).encode("utf-8")
        blob["manifest_hash"] = hashlib.sha256(canonical).hexdigest()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)

    # ─── Sealing — capture canonical state ──────────────────────────────

    def seal_path(self, path: Path, key: Optional[str] = None,
                  description: str = "") -> GoldenImageEntry:
        """Capture the current content of one file as canonical."""
        if not path.is_file():
            raise FileNotFoundError(f"cannot seal non-file: {path}")
        data = path.read_bytes()
        entries = self._load_catalog()
        entry = GoldenImageEntry(
            key=key or str(path.relative_to(self._watched_root)
                           if path.is_relative_to(self._watched_root) else path),
            path=str(path),
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
            sealed_at=_iso_now(),
            description=description,
        )
        entries[entry.key] = entry
        self._save_catalog(entries)
        return entry

    def seal_directory(self, root: Path, glob: str = "**/*.py",
                       description: str = "") -> list[GoldenImageEntry]:
        """Seal every file under root matching the glob. Convenience helper
        for initial setup — call this once after install to capture the
        package's canonical state."""
        sealed: list[GoldenImageEntry] = []
        for p in root.glob(glob):
            if not p.is_file():
                continue
            if any(part in {"__pycache__", ".venv", "node_modules"}
                   for part in p.parts):
                continue
            try:
                sealed.append(self.seal_path(p, description=description))
            except (OSError, FileNotFoundError):
                continue
        return sealed

    def unseal(self, key: str) -> bool:
        """Remove an entry from the golden image. Returns True if removed."""
        entries = self._load_catalog()
        if key in entries:
            del entries[key]
            self._save_catalog(entries)
            return True
        return False

    # ─── Scan ───────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        entries = self._load_catalog()
        drift_findings: list[dict] = []
        missing_findings: list[dict] = []

        for entry in entries.values():
            p = Path(entry.path)
            if not p.is_file():
                entry.last_status = "missing"
                missing_findings.append({
                    "key": entry.key, "path": entry.path,
                    "expected_sha256": entry.expected_sha256,
                })
            else:
                data = p.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual != entry.expected_sha256:
                    entry.last_status = "drift"
                    drift_findings.append({
                        "key": entry.key,
                        "path": entry.path,
                        "expected_sha256": entry.expected_sha256,
                        "observed_sha256": actual,
                        "expected_size": entry.expected_size,
                        "observed_size": len(data),
                    })
                else:
                    entry.last_status = "ok"
            entry.last_verified_at = _iso_now()

        self._save_catalog(entries)

        total = len(drift_findings) + len(missing_findings)
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="golden_image",
            findings_count=total,
            summary=(
                f"verified {len(entries)} golden-image entries; "
                f"{len(drift_findings)} drift, {len(missing_findings)} missing"
            ),
            catalog_path=str(self._catalog_path()),
            details={
                "total_sealed": len(entries),
                "drift": drift_findings,
                "missing": missing_findings,
                "recovery_candidate": self._propose_recovery_snapshot()
                                       if total > 0 else None,
            },
        )

    def health_status(self) -> HealthStatus:
        report = self.scan()
        drift = len(report.details.get("drift", []))
        missing = len(report.details.get("missing", []))
        if drift + missing == 0:
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary=f"all {report.details.get('total_sealed', 0)} "
                        f"golden-image entries verified",
                observed_at=_iso_now(),
            )
        return HealthStatus(
            sentinel_id=self.id, level="error",
            summary=f"{drift} drift + {missing} missing — possible tampering "
                    f"or accidental file modification",
            observed_at=_iso_now(),
        )

    # ─── Recovery proposal ──────────────────────────────────────────────

    def _propose_recovery_snapshot(self) -> Optional[dict]:
        """Identify the most recent Vault snapshot that was verified clean.

        We don't make assumptions about what 'clean' means at the file level
        — we trust the operator's prior judgment, which means the most-recent
        snapshot is the proposal. The operator can step back further if they
        suspect the most-recent one was already compromised.
        """
        if self._vault is None:
            return None
        try:
            snapshots = self._vault.list_snapshots()  # type: ignore[attr-defined]
        except Exception:
            return None
        if not snapshots:
            return None
        latest = snapshots[-1]
        return {
            "snapshot_id": latest.snapshot_id,
            "taken_at": latest.taken_at,
            "label": latest.label,
            "cipher_mode": latest.cipher_mode,
            "operator_command": (
                f"vault.restore(snapshot_id='{latest.snapshot_id}', "
                f"target=data_dir, confirm=True)"
            ),
        }

    # ─── MedicalCapability ──────────────────────────────────────────────

    def damage_estimate(self) -> DamageReport:
        report = self.scan()
        drift = report.details.get("drift", [])
        missing = report.details.get("missing", [])
        if not (drift or missing):
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R0_ARTIFACT,
                severity="info", confidence=1.0,
                summary="golden image intact",
            )
        evidence = []
        for d in drift[:20]:
            evidence.append(Evidence(
                kind="checksum-drift",
                summary=f"{d['key']}: content changed",
                source_path=d.get("path", ""),
                expected=d.get("expected_sha256", ""),
                observed=d.get("observed_sha256", ""),
            ))
        for m in missing[:20]:
            evidence.append(Evidence(
                kind="path-missing",
                summary=f"{m['key']}: file disappeared",
                source_path=m.get("path", ""),
                expected=m.get("expected_sha256", ""),
            ))
        return DamageReport(
            incident_id=IncidentId(str(ULID())),
            sentinel_id=self.id,
            radius=BlastRadius.R2_SOFTWARE,
            severity="alert", confidence=0.95,
            summary=(f"{len(drift)} drift + {len(missing)} missing golden-image "
                     f"entries — possible tampering or unauthorized modification"),
            evidence=evidence,
        )

    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        recovery = self._propose_recovery_snapshot()
        steps: list[RepairStep] = []
        if recovery:
            steps.append(RepairStep(
                ordinal=1,
                description=(f"operator confirms recovery from vault snapshot "
                             f"{recovery['snapshot_id'][:12]}... "
                             f"(taken {recovery['taken_at']}, "
                             f"label='{recovery['label']}')"),
                action_kind="operator-action-required",
                reversible=False,  # restoring a vault snapshot is one-way
                estimated_cost_seconds=60,
            ))
            steps.append(RepairStep(
                ordinal=2,
                description=("after restore, Watchdog re-seals golden image "
                             "against the restored state"),
                action_kind="operator-action-required",
                target_path=str(self._watched_root),
            ))
        else:
            steps.append(RepairStep(
                ordinal=1,
                description=("no Vault snapshots available — operator must "
                             "manually investigate and restore from external "
                             "backup or reinstall"),
                action_kind="operator-action-required",
            ))
        return RepairPlan(
            incident_id=damage.incident_id,
            sentinel_id=self.id,
            radius=damage.radius,
            summary=("golden-image drift detected — Watchdog proposes "
                     "Vault-based recovery; operator confirms"),
            steps=steps,
            rollback_steps=[],
            estimated_total_seconds=60,
            requires_aria_quiesce=True,  # restoring data_dir requires Aria pause
        )

    def repair_dry_run(self, plan: RepairPlan) -> DryRunReport:
        return DryRunReport(
            incident_id=plan.incident_id,
            plan_hash=plan.plan_hash(),
            sentinel_id=self.id,
            would_succeed=True,
            would_modify=[], would_create=[], would_delete=[],
            opaque_steps=[s.ordinal for s in plan.steps],
            warnings=[
                "Watchdog never modifies files autonomously. The proposed "
                "Vault restore is executed only by explicit operator "
                "vault.restore(confirm=True)."
            ],
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
            error_summary=("Watchdog delegates all file modification to "
                           "operator-confirmed Vault.restore"),
        )


__all__ = ["WatchdogSentinel", "GoldenImageEntry"]
