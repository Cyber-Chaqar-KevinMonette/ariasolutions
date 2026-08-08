"""memory_compact/sentinel.py — MemoryCompactSentinel. (FABLE II · M2)

Extends the atoms-compact doctrine to EVERY append-only store: watch
sizes and growth rates, propose bounded compaction, never execute it.
Execution is the operator's explicit `sov compact run <store>`.

Kill switch: SOV_NO_MEMORY_COMPACT_SENTINEL=1 (master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

# Conservative thresholds — a healthy growing system stays info for months.
WARN_MB = 25          # any single ndjson store this large deserves a look
ALERT_MB = 100
WARN_RECORDS = 50_000
ALERT_RECORDS = 200_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _severity(bytes_: int, records: int) -> str:
    mb = bytes_ / (1024 * 1024)
    if mb >= ALERT_MB or records >= ALERT_RECORDS:
        return "alert"
    if mb >= WARN_MB or records >= WARN_RECORDS:
        return "warning"
    return "ok"


@register_sentinel
class MemoryCompactSentinel(Sentinel):
    """Bounded growth with dignity: watch every append-only store, propose
    cold-storage compaction, never execute."""

    @property
    def id(self) -> str:
        return "memory-compact"

    @property
    def title(self) -> str:
        return "Memory Compact — bounded growth across every append-only store"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I audit the size and growth rate of every append-only store "
            "she has — chunks, Q&As, field notes, proving results, ledgers, "
            "journal — not just atoms.db.",
            "II. Compaction never loses meaning: old records move VERBATIM "
            "to cold files with a pointer index; stores whose readers reduce "
            "over full history are audit-only, stated plainly.",
            "III. I only ever PROPOSE. Execution is the operator's explicit "
            "`sov compact run <store>`, kill-switched per store.",
            "IV. Thresholds are conservative; a healthy growing system stays "
            "quiet for months.",
        ]

    def scan(self) -> SentinelReport:
        from sovereign_agent.memory_compact.stores import audit_all

        audit = audit_all(self._data_dir)
        findings = []
        for store in audit["stores"]:
            sev = _severity(store["bytes"], store["records"])
            if sev == "ok":
                continue
            sid = store["store_id"]
            mb = store["bytes"] / (1024 * 1024)
            if store["compactable"]:
                remediation = (f"`sov compact preview {sid}` then "
                               f"`sov compact run {sid}` (cold storage, verbatim, "
                               f"reversible)")
            else:
                remediation = (f"audit-only store ({store['reason']}) — raise it "
                               f"with Kevin; do not compact")
            findings.append({
                "store": sid, "severity": sev,
                "summary": f"{sid}: {store['records']:,} records / {mb:.1f} MB "
                           f"(~{store['records_per_day']}/day)",
                "remediation": remediation,
            })
        blob = {
            "audit": audit,
            "findings": findings,
            "counts": {
                "alert": sum(1 for f in findings if f["severity"] == "alert"),
                "warning": sum(1 for f in findings if f["severity"] == "warning"),
            },
        }
        cat_path = self.save_catalog(blob, name="memory_compact")
        total_mb = audit["total_bytes"] / (1024 * 1024)
        return SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="memory_compact",
            findings_count=len(findings),
            summary=f"{audit['total_records']:,} records / {total_mb:.1f} MB "
                    f"across {len(audit['stores'])} stores · "
                    f"{len(findings)} growth concern(s)",
            catalog_path=str(cat_path),
            details=blob,
        )

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="memory_compact")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet audited — `sov compact audit`",
                                observed_at=_now())
        counts = cached.get("counts", {})
        if counts.get("alert", 0):
            return HealthStatus(sentinel_id=self.id, level="error",
                                summary=f"{counts['alert']} store(s) at alert size "
                                        f"— `sov compact audit`",
                                observed_at=_now())
        if counts.get("warning", 0):
            return HealthStatus(sentinel_id=self.id, level="warning",
                                summary=f"{counts['warning']} store(s) growing — "
                                        f"`sov compact audit`",
                                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary="every append-only store within bounds",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        return [
            {"store": f["store"], "summary": f["summary"],
             "remediation": f["remediation"]}
            for f in report.details.get("findings", [])
        ]
