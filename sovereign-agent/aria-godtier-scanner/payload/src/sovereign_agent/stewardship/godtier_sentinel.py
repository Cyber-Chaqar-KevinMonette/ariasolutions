"""stewardship/godtier_sentinel.py — the standing god-tier self-scan.

Periodically holds the whole system to GOD_TIER_CANON.md and surfaces every sub-god-tier target. Propose-
only: she reports; the operator (or a supervised autonomy session) acts. This is how nothing gets neglected.
"""
from __future__ import annotations

from pathlib import Path

from .base import Sentinel, SentinelReport, HealthStatus, _iso_now
from .registry import register_sentinel


@register_sentinel
class GodTierSentinel(Sentinel):
    """Standing self-scan against the god-tier canon — total coverage, propose-only."""

    @property
    def id(self) -> str:
        return "godtier"

    @property
    def title(self) -> str:
        return "God-Tier Scanner — holds the whole system to the canon"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I hold every system to the god-tier canon. Total coverage — nothing is neglected.",
            "I report every weak, fragile, or neglected target transparently.",
            "I propose god-tier enhancements; I never apply them. A human acts.",
            "The floor only ratchets up. I never lower a standard to make a target pass.",
        ]

    def _scan(self):
        from sovereign_agent.godtier import scanner
        repo = self._data_dir
        # walk up to the repo root (where scripts/ + aria-* live)
        for up in [Path.cwd(), *Path(__file__).resolve().parents]:
            if (up / "scripts" / "lib" / "god_tier_canon.json").exists():
                repo = up
                break
        return scanner.scan(repo)

    def scan(self) -> SentinelReport:
        observed = _iso_now()
        try:
            rep = self._scan()
            below = rep["bands"].get("neglected", 0) + rep["bands"].get("weak", 0) + rep["bands"].get("fragile", 0)
            summary = (f"{rep['total_targets']} targets · avg {rep['average_score']} · "
                       f"{int(rep['god_tier_fraction']*100)}% god-tier · {below} below god-tier")
            path = self.save_catalog(rep, name="godtier-scan")
            if rep["bands"].get("neglected", 0) > 0:
                self.notify("warning", "Neglected systems found",
                            f"{rep['bands']['neglected']} neglected target(s) — see god-tier scan.",
                            addressed_to="both", data={"weakest": rep["weakest"][:5]})
            return SentinelReport(sentinel_id=self.id, observed_at=observed, catalog_name="godtier-scan",
                                  findings_count=below, summary=summary, catalog_path=str(path),
                                  details={"bands": rep["bands"], "average": rep["average_score"]})
        except Exception as exc:  # noqa: BLE001
            return SentinelReport(sentinel_id=self.id, observed_at=observed, catalog_name="godtier-scan",
                                  findings_count=0, summary=f"scan unavailable: {exc!r}", details={})

    def health_status(self) -> HealthStatus:
        try:
            rep = self._scan()
            frac = rep["god_tier_fraction"]
            level = "ok" if frac >= 0.6 else "warning"
            return HealthStatus(sentinel_id=self.id, level=level,
                                summary=f"{int(frac*100)}% god-tier ({rep['total_targets']} targets)",
                                observed_at=_iso_now())
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(sentinel_id=self.id, level="unknown",
                                summary=f"unavailable: {exc!r}", observed_at=_iso_now())
