"""backup_sentinel.py — backups that happen without being asked.

Kill switch: SOV_NO_BACKUP_SENTINEL=1 (honored by Sentinel.is_enabled(),
checked by the registry's gather_health/scan_all and by the cockpit's
auto-backup worker).

THE GAP THIS CLOSES: backup.py's snapshot() is excellent (SHA-256 manifest,
online SQLite backup, never-zero-backups pruning, Tier-3 gated restore) but
was operator-invoked ONLY — nothing ever triggered it automatically.
atoms.db holds the lessons table and the honor ledger: corruption without a
recent manual snapshot meant permanent loss of her memories.

THE ONE DELIBERATE EXCEPTION TO PROPOSE-ONLY, stated plainly: scan() TAKES
a snapshot (and verifies it) when the newest one is older than the cadence,
rather than merely proposing one. Justification: a snapshot is purely
additive and protective — it creates a new directory and never modifies or
deletes live state (pruning stays inside backup.py's own never-zero-backups
policy; RESTORE stays Tier-3 human-gated and this sentinel never calls it).
A protective action that cannot damage anything is the one place automation
outranks ceremony.

Backup-root resolution ("backups live BESIDE the data_dir they protect"):
  1. SOV_BACKUP_ROOT env var, if set (operator override / test isolation).
  2. If this sentinel's data_dir IS the production SETTINGS data_dir:
     backup.default_backup_root() — the same root manual snapshots use, so
     the cadence check sees operator-taken snapshots too.
  3. Otherwise (a foreign/test data_dir): a sibling of THAT data_dir —
     mirroring default_backup_root()'s own sibling-not-child rule, and
     guaranteeing a test-constructed sentinel can never write into the real
     backup root.

health_status() is CHEAP (reads snapshot manifests + age math only — never
verifies hashes, never snapshots): gather_health() runs on the cockpit's 8s
strip cadence. scan() is the real work, invoked by `sov sentinels scan`,
scan_all(), or the cockpit's hourly auto-backup timer.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .base import HealthStatus, Sentinel, SentinelReport
from .registry import register_sentinel

DEFAULT_CADENCE_HOURS = 24.0
CADENCE_ENV = "SOV_BACKUP_CADENCE_HOURS"


def _cadence_hours() -> float:
    raw = os.environ.get(CADENCE_ENV, "")
    try:
        val = float(raw)
        return val if val > 0 else DEFAULT_CADENCE_HOURS
    except ValueError:
        return DEFAULT_CADENCE_HOURS


def _snapshot_age_hours(created_at: str) -> float | None:
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


@register_sentinel
class BackupSentinel(Sentinel):
    """Keeps a fresh, verified whole-data_dir snapshot on a cadence.

    Kill switch: SOV_NO_BACKUP_SENTINEL=1
    """

    @property
    def id(self) -> str:
        return "backup"

    @property
    def title(self) -> str:
        return "Auto-Backup — a fresh, verified snapshot of her memories on a cadence"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I keep the newest verified snapshot younger than the cadence "
            f"(default {DEFAULT_CADENCE_HOURS:g}h, tunable via {CADENCE_ENV}).",
            "II. Snapshots are purely additive — I never modify or delete live "
            "state, and pruning stays inside backup.py's own never-zero-backups "
            "policy.",
            "III. I NEVER restore. Restore is Tier-3, human-gated, and stays "
            "that way.",
            "IV. I verify every snapshot I take (manifest hash + file hashes) "
            "and report honestly when verification fails.",
            "V. Backups for a data_dir live beside THAT data_dir — I can never "
            "write a test data_dir's snapshots into the production backup root.",
        ]

    # ── root resolution ──────────────────────────────────────────────────

    def _backup_root(self) -> Path:
        env = os.environ.get("SOV_BACKUP_ROOT", "")
        if env:
            return Path(env)
        from sovereign_agent import backup as _bk
        from sovereign_agent.config import SETTINGS

        if Path(self._data_dir) == SETTINGS.paths.data_dir:
            return _bk.default_backup_root()
        # Foreign (test/alternate) data_dir: sibling of that dir, mirroring
        # default_backup_root()'s own sibling-not-child rule.
        return Path(self._data_dir).parent / "sovereign-agent-backups"

    def _newest_snapshot(self):
        """(manifest | None) for the newest snapshot at the resolved root."""
        from sovereign_agent import backup as _bk

        root = self._backup_root()
        if not root.exists():
            return None
        snaps = _bk.list_snapshots(backup_root=root)
        return snaps[0] if snaps else None

    def overdue(self) -> bool:
        newest = self._newest_snapshot()
        if newest is None:
            return True
        age = _snapshot_age_hours(newest.created_at)
        return age is None or age > _cadence_hours()

    # ── the real work ────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        """If the newest snapshot is older than the cadence: take one, verify
        it, and record the outcome. Otherwise report the healthy state."""
        from sovereign_agent import backup as _bk

        root = self._backup_root()
        took = False
        verify_ok: bool | None = None
        error = ""
        snapshot_id = ""

        if self.overdue():
            try:
                manifest = _bk.snapshot(
                    backup_root=root, data_dir=Path(self._data_dir),
                )
                snapshot_id = manifest.snapshot_id
                took = True
                result = _bk.verify(snapshot_id, backup_root=root, run_audit=False)
                verify_ok = bool(result.ok)
                if not result.ok:
                    error = result.error or "verify failed"
            except Exception as exc:  # noqa: BLE001 — report, never crash the scan loop
                error = repr(exc)
        else:
            newest = self._newest_snapshot()
            snapshot_id = newest.snapshot_id if newest else ""

        newest = self._newest_snapshot()
        age_hours = _snapshot_age_hours(newest.created_at) if newest else None
        blob = {
            "backup_root": str(root),
            "cadence_hours": _cadence_hours(),
            "took_snapshot": took,
            "snapshot_id": snapshot_id,
            "verify_ok": verify_ok,
            "newest_age_hours": age_hours,
            "error": error,
        }
        cat_path = self.save_catalog(blob, name="auto_backup")

        healthy = (not error) and (newest is not None)
        findings = 0 if healthy else 1
        if took and verify_ok:
            summary = f"took + verified snapshot {snapshot_id}"
        elif took and not verify_ok:
            summary = f"took snapshot {snapshot_id} but VERIFY FAILED: {error}"
        elif error:
            summary = f"snapshot attempt failed: {error}"
        else:
            summary = (
                f"fresh — newest snapshot {snapshot_id} is "
                f"{age_hours:.1f}h old (cadence {_cadence_hours():g}h)"
                if age_hours is not None else "fresh"
            )
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            catalog_name="auto_backup",
            findings_count=findings,
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )

    # ── the cheap read ───────────────────────────────────────────────────

    def health_status(self) -> HealthStatus:
        """Cheap: manifest reads + age math only. Never verifies hashes,
        never snapshots — gather_health() runs on an 8s cockpit cadence."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            newest = self._newest_snapshot()
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"cannot read backup root: {exc!r}", observed_at=now,
            )
        cadence = _cadence_hours()
        if newest is None:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary="no snapshots yet — first auto-backup pending "
                        "(or run `sov backup snapshot` now)",
                observed_at=now,
            )
        age = _snapshot_age_hours(newest.created_at)
        cached = self.load_catalog(name="auto_backup") or {}
        last_verify_ok = cached.get("verify_ok")
        if last_verify_ok is False:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"last auto-backup verify FAILED: {cached.get('error', '')}",
                observed_at=now,
            )
        if age is None or age > 3 * cadence:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"newest snapshot is {age:.0f}h old — more than 3x the "
                        f"{cadence:g}h cadence" if age is not None
                        else "newest snapshot has an unreadable timestamp",
                observed_at=now,
            )
        if age > cadence:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"newest snapshot is {age:.1f}h old (cadence {cadence:g}h) "
                        "— auto-backup due",
                observed_at=now,
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary=f"newest snapshot is {age:.1f}h old (cadence {cadence:g}h)",
            observed_at=now,
        )
