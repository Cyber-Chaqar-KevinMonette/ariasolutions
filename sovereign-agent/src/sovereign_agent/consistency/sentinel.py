"""consistency/sentinel.py — the ConsistencySentinel. (FABLE II · M1)

Checks the JOINS the way loose-threads checks the calls: her memory
organs are individually excellent; this sentinel watches them AGREE.

Kill switch: SOV_NO_ONE_TRUTH_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).

scan() runs every named join check (cheap — bounded file reads plus a
few targeted greps, no repo-wide AST) and caches the catalog; health_
status() reads the cache only (the standing strip discipline). Health is
WARN-level when any join disagrees — disagreement is drift, not fire.
Findings carry repair PROPOSALS; nothing is ever auto-repaired.
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@register_sentinel
class ConsistencySentinel(Sentinel):
    """One life, one truth: cross-store joins observed, never repaired."""

    @property
    def id(self) -> str:
        return "one-truth"

    @property
    def title(self) -> str:
        return "One Truth — cross-store consistency (the joins between her memory organs)"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I check the JOINS between her memory organs — thread to "
            "chunks, sessions to scopes to rest point, lessons to retrain "
            "marker, wonders to uncertainties, scores to suites, "
            "dispositions to symbols. Each join is one named check with a "
            "mechanical verdict.",
            "II. I never repair. Every finding carries a repair PROPOSAL "
            "the operator can act on — the diagnosis.py discipline: no "
            "resolution without a human and a rollback path.",
            "III. Disagreement is drift, not fire: my health is warn-level. "
            "I say plainly which organ disagrees with which, and about what.",
            "IV. A store that does not exist yet cannot disagree — absence "
            "is honest, never a finding.",
        ]

    def scan(self) -> SentinelReport:
        from sovereign_agent.consistency.checks import run_all

        results = run_all(self._data_dir)
        findings = [f.as_dict() for r in results for f in r.findings]
        blob = {
            "checks": [r.as_dict() for r in results],
            "checks_run": len(results),
            "checks_clean": sum(1 for r in results if r.ok),
            "findings_count": len(findings),
        }
        cat_path = self.save_catalog(blob, name="one_truth")
        clean = blob["checks_clean"]
        return SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="one_truth",
            findings_count=len(findings),
            summary=f"{clean}/{len(results)} joins agree · "
                    f"{len(findings)} disagreement(s)",
            catalog_path=str(cat_path),
            details=blob,
        )

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="one_truth")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov truth`",
                                observed_at=_now())
        n = int(cached.get("findings_count", 0))
        if n == 0:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="every join agrees — one truth",
                                observed_at=_now())
        return HealthStatus(
            sentinel_id=self.id, level="warning",
            summary=f"{n} cross-store disagreement(s) — `sov truth` for proposals",
            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        """The repair proposals, surfaced as the base contract intends."""
        out: list[dict] = []
        for check in report.details.get("checks", []):
            for f in check.get("findings", []):
                out.append({"check": f.get("check_id"), "subject": f.get("subject"),
                            "proposal": f.get("proposal")})
        return out
