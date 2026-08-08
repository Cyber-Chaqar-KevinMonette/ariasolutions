"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/atoms_compact_sentinel.py — atom store growth watchdog    ║
║                                                                           ║
║  RISK-008: append-only stores grow unbounded. This sentinel monitors    ║
║  atoms.db health and proposes compaction when the store drifts into     ║
║  growth territory that will affect query latency or disk consumption.   ║
║                                                                           ║
║  Binding statements                                                       ║
║                                                                           ║
║    I. I track the total atom count, DB file size, and age distribution.  ║
║                                                                           ║
║   II. I report the distribution of atom types so growth hot-spots        ║
║       are visible to the operator.                                       ║
║                                                                           ║
║  III. I flag superseded-atom accumulation — superseded atoms slow        ║
║       active queries and should be periodically summarized.             ║
║                                                                           ║
║   IV. I NEVER delete or modify atoms. I propose; the operator decides.  ║
║       Compaction means writing a summary atom + marking originals        ║
║       superseded — the audit trail is always intact.                   ║
║                                                                           ║
║    V. Thresholds are conservative. A healthy growing system should        ║
║       stay at info-level for months before hitting warning.             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import HealthStatus, Sentinel, SentinelReport
from .registry import register_sentinel

# Thresholds — conservative by design
_WARN_COUNT = 5_000      # atoms; warning at this total
_ALERT_COUNT = 20_000    # atoms; alert at this total
_WARN_MB = 100           # MB; warning on DB file size
_ALERT_MB = 500          # MB; alert on DB file size
_WARN_SUPERSEDED_PCT = 40  # % superseded; warning
_ALERT_SUPERSEDED_PCT = 60  # % superseded; alert
_OLD_DAYS = 90           # atoms older than this → info notice


@dataclass
class CompactFinding:
    """One specific atoms-store issue."""
    kind: str       # 'count', 'size', 'superseded', 'age', 'hotspot'
    severity: str   # 'info' / 'warning' / 'alert'
    summary: str
    detail: str = ""
    remediation: str = ""


@register_sentinel
class AtomsCompactSentinel(Sentinel):
    """Watches atoms.db for unbounded growth and proposes compaction."""

    @property
    def id(self) -> str:
        return "atoms-compact"

    @property
    def title(self) -> str:
        return "Atoms store compaction sentinel"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I track total atom count, DB file size, and age distribution.",
            "I report atom-type distribution so growth hot-spots are visible.",
            "I flag superseded-atom accumulation that slows active queries.",
            "I never delete or modify atoms — I propose; the operator decides.",
            "Compaction proposals use atoms_compact_preview() before atoms_compact().",
            "Conservative thresholds: a healthy system stays info-level for months.",
        ]

    # ── Scanning ─────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        findings: list[CompactFinding] = []

        try:
            stats = self._gather_stats()
        except Exception as exc:  # noqa: BLE001
            stats = None
            findings.append(CompactFinding(
                kind="scan-error",
                severity="warning",
                summary=f"Could not read atoms.db: {exc}",
                remediation="Ensure the DB is accessible and not locked.",
            ))

        if stats:
            findings.extend(self._check_count(stats))
            findings.extend(self._check_size(stats))
            findings.extend(self._check_superseded(stats))
            findings.extend(self._check_age(stats))
            findings.extend(self._check_hotspot(stats))

        catalog = {
            "scanned_at": self._iso_now(),
            "stats": stats or {},
            "findings": [
                {
                    "kind": f.kind, "severity": f.severity,
                    "summary": f.summary, "detail": f.detail,
                    "remediation": f.remediation,
                }
                for f in findings
            ],
            "counts": {
                "alert":   sum(1 for f in findings if f.severity == "alert"),
                "warning": sum(1 for f in findings if f.severity == "warning"),
                "info":    sum(1 for f in findings if f.severity == "info"),
            },
        }
        catalog_path = self.save_catalog(catalog, name="default")

        for f in findings:
            if f.severity == "alert":
                self.notify(
                    severity="alert",
                    title=f.summary,
                    message=f.detail + (f"\n\nSuggested fix:\n  {f.remediation}" if f.remediation else ""),
                    addressed_to="both",
                    data={"kind": f.kind},
                )

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=self._iso_now(),
            catalog_name="default",
            findings_count=len(findings),
            summary=(
                f"{catalog['counts']['alert']} alert, "
                f"{catalog['counts']['warning']} warning, "
                f"{catalog['counts']['info']} info"
                + (f" — {stats['total']} atoms / {stats['db_mb']:.1f} MB" if stats else "")
            ),
            catalog_path=str(catalog_path),
            details={"counts": catalog["counts"], "stats": stats or {}},
        )

    def health_status(self) -> HealthStatus:
        catalog = self.load_catalog("default")
        if catalog is None:
            return HealthStatus(
                sentinel_id=self.id, level="unknown",
                summary="never scanned (run `sov sentinels scan atoms-compact`)",
            )
        counts = catalog.get("counts", {})
        stats = catalog.get("stats", {})
        size_note = f"{stats.get('total', '?')} atoms / {stats.get('db_mb', '?')} MB"
        if counts.get("alert", 0) > 0:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"atoms store alert — {size_note}",
                detail="Run `sov sentinels show atoms-compact` for details.",
            )
        if counts.get("warning", 0) > 0:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"atoms store warning — {size_note}",
                detail="Run `sov sentinels show atoms-compact` for details.",
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary=f"atoms store healthy — {size_note}",
            detail=f"last scan {catalog.get('scanned_at', '?')}",
        )

    def proposals(self, report: SentinelReport) -> list[dict]:
        catalog = self.load_catalog("default")
        if catalog is None:
            return []
        return [
            {"kind": f["kind"], "summary": f["summary"], "remediation": f["remediation"]}
            for f in catalog.get("findings", [])
            if f.get("remediation")
        ]

    # ── Stats gathering ───────────────────────────────────────────────────

    def _gather_stats(self) -> dict:
        import sqlite3

        db_path = self._db_path()
        db_mb = db_path.stat().st_size / (1024 * 1024) if db_path.is_file() else 0.0

        conn = sqlite3.connect(str(db_path))
        try:
            total = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM atoms WHERE superseded_at IS NULL"
            ).fetchone()[0]
            superseded = total - active

            cutoff = (datetime.now(timezone.utc) - timedelta(days=_OLD_DAYS)).isoformat()
            old_count = conn.execute(
                "SELECT COUNT(*) FROM atoms WHERE created_at < ?", (cutoff,)
            ).fetchone()[0]

            type_rows = conn.execute(
                "SELECT type, COUNT(*) FROM atoms GROUP BY type ORDER BY COUNT(*) DESC LIMIT 20"
            ).fetchall()
            by_type = {r[0]: r[1] for r in type_rows}

            oldest_row = conn.execute(
                "SELECT MIN(created_at) FROM atoms"
            ).fetchone()
            oldest_at = oldest_row[0] if oldest_row else None

        finally:
            conn.close()

        superseded_pct = round(100 * superseded / total, 1) if total else 0.0

        return {
            "total": total,
            "active": active,
            "superseded": superseded,
            "superseded_pct": superseded_pct,
            "old_count": old_count,
            "old_days": _OLD_DAYS,
            "by_type": by_type,
            "db_mb": round(db_mb, 2),
            "oldest_at": oldest_at,
        }

    # ── Individual checks ─────────────────────────────────────────────────

    def _check_count(self, stats: dict) -> list[CompactFinding]:
        total = stats["total"]
        if total >= _ALERT_COUNT:
            return [CompactFinding(
                kind="count",
                severity="alert",
                summary=f"Atom store has {total:,} atoms — query performance degraded",
                detail=(
                    f"The atoms table has {total:,} rows. Active queries scan this table "
                    f"on every turn. Above {_ALERT_COUNT:,} atoms, latency will be noticeable."
                ),
                remediation=(
                    "Use atoms_compact_preview(before_days=90) to see what compaction would do,\n"
                    "then atoms_compact(before_days=90) to write summary atoms and supersede originals."
                ),
            )]
        if total >= _WARN_COUNT:
            return [CompactFinding(
                kind="count",
                severity="warning",
                summary=f"Atom store has {total:,} atoms — approaching compaction threshold",
                detail=f"Alert threshold is {_ALERT_COUNT:,}. Consider scheduling compaction.",
                remediation="atoms_compact_preview(before_days=90) to preview compaction.",
            )]
        return []

    def _check_size(self, stats: dict) -> list[CompactFinding]:
        mb = stats["db_mb"]
        if mb >= _ALERT_MB:
            return [CompactFinding(
                kind="size",
                severity="alert",
                summary=f"atoms.db is {mb:.0f} MB — disk consumption critical",
                detail=f"The database file is large. Alert threshold is {_ALERT_MB} MB.",
                remediation="Run atoms_compact(before_days=90) followed by `VACUUM` on the DB.",
            )]
        if mb >= _WARN_MB:
            return [CompactFinding(
                kind="size",
                severity="warning",
                summary=f"atoms.db is {mb:.0f} MB — growing",
                detail=f"Warning threshold is {_WARN_MB} MB.",
                remediation="Monitor growth rate; consider compaction if trend continues.",
            )]
        return []

    def _check_superseded(self, stats: dict) -> list[CompactFinding]:
        pct = stats["superseded_pct"]
        count = stats["superseded"]
        if pct >= _ALERT_SUPERSEDED_PCT:
            return [CompactFinding(
                kind="superseded",
                severity="alert",
                summary=f"{pct:.0f}% of atoms are superseded ({count:,}) — store bloated",
                detail=(
                    "Superseded atoms are never deleted (audit trail) but slow active-only queries.\n"
                    f"Alert threshold is {_ALERT_SUPERSEDED_PCT}%."
                ),
                remediation=(
                    "After compaction, run: VACUUM on atoms.db to reclaim space.\n"
                    "Superseded atoms remain in DB — audit trail is intact."
                ),
            )]
        if pct >= _WARN_SUPERSEDED_PCT:
            return [CompactFinding(
                kind="superseded",
                severity="warning",
                summary=f"{pct:.0f}% of atoms are superseded ({count:,})",
                detail=f"Warning threshold is {_WARN_SUPERSEDED_PCT}%.",
                remediation="Consider compaction to summarize old clusters.",
            )]
        return []

    def _check_age(self, stats: dict) -> list[CompactFinding]:
        old = stats["old_count"]
        if old > 0:
            oldest = stats.get("oldest_at", "?")
            return [CompactFinding(
                kind="age",
                severity="info",
                summary=f"{old} atom(s) older than {_OLD_DAYS} days (oldest: {oldest[:10] if oldest else '?'})",
                detail=(
                    f"Atoms older than {_OLD_DAYS} days are candidates for compaction.\n"
                    "They remain fully readable but can be summarized to save query time."
                ),
                remediation=f"atoms_compact_preview(before_days={_OLD_DAYS}) to see compaction candidates.",
            )]
        return []

    def _check_hotspot(self, stats: dict) -> list[CompactFinding]:
        total = stats["total"]
        if total == 0:
            return []
        by_type = stats["by_type"]
        findings = []
        for atom_type, count in by_type.items():
            pct = 100 * count / total
            if pct >= 50:
                findings.append(CompactFinding(
                    kind="hotspot",
                    severity="info",
                    summary=f"Type '{atom_type}' is {pct:.0f}% of all atoms ({count})",
                    detail=(
                        f"One atom type dominates the store. If '{atom_type}' atoms "
                        "accumulate fast (e.g., heartbeat, lesson, experience), "
                        "type-targeted compaction is most effective."
                    ),
                    remediation=f"atoms_compact_preview(before_days=30, atom_type='{atom_type}')",
                ))
        return findings

    # ── Helpers ──────────────────────────────────────────────────────────

    def _db_path(self) -> Path:
        try:
            from sovereign_agent.db import open_atoms_db
            conn = open_atoms_db()
            p = Path(conn.execute("PRAGMA database_list").fetchone()[2])
            conn.close()
            return p
        except Exception:  # noqa: BLE001
            pass
        data_dir = Path(os.environ.get("SOV_DATA_DIR", Path.home() / ".local/share/sovereign-agent"))
        return data_dir / "atoms.db"

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["AtomsCompactSentinel", "CompactFinding"]
