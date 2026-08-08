"""stewardship/resilience_sentinel.py — standing resilience scan of both layers.

Periodically probes the classical + non-classical entry points with the edge battery and flags anything that
wedges (crashes/hangs on a weird input). Propose-only — it reports; the operator hardens. Defensive.
"""
from __future__ import annotations

from .base import Sentinel, SentinelReport, HealthStatus, _iso_now
from .registry import register_sentinel


@register_sentinel
class ResilienceSentinel(Sentinel):
    """Standing edge-case resilience scan across both layers — total coverage, propose-only."""

    @property
    def id(self) -> str:
        return "resilience"

    @property
    def title(self) -> str:
        return "Resilience Scanner — both layers degrade gracefully on every edge input"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I probe every system with adversarial edge inputs (empty/huge/malformed/unicode/timeout).",
            "A god-tier system never wedges — it degrades to a clear value or status.",
            "I cover BOTH the classical and the non-classical layer.",
            "I report what wedges; I never weaken a check to make it pass.",
        ]

    def scan(self) -> SentinelReport:
        observed = _iso_now()
        try:
            from sovereign_agent.resilience_scan import layers
            rep = layers.scan_both_layers()
            wedged = []
            for layer in ("classical", "non_classical"):
                for t in rep[layer]["targets"]:
                    if t.get("resilient") is False:
                        wedged.append(t["target"])
            summary = (f"both layers resilient" if rep["both_layers_resilient"]
                       else f"{len(wedged)} entry point(s) wedge: {', '.join(wedged)}")
            path = self.save_catalog(rep, name="resilience-scan")
            if wedged:
                self.notify("warning", "Resilience wedge found", summary, addressed_to="both",
                            data={"wedged": wedged})
            return SentinelReport(sentinel_id=self.id, observed_at=observed, catalog_name="resilience-scan",
                                  findings_count=len(wedged), summary=summary, catalog_path=str(path),
                                  details={"both_layers_resilient": rep["both_layers_resilient"]})
        except Exception as exc:  # noqa: BLE001
            return SentinelReport(sentinel_id=self.id, observed_at=observed, catalog_name="resilience-scan",
                                  findings_count=0, summary=f"scan unavailable: {exc!r}", details={})

    def health_status(self) -> HealthStatus:
        try:
            from sovereign_agent.resilience_scan import layers
            ok = layers.scan_both_layers()["both_layers_resilient"]
            return HealthStatus(sentinel_id=self.id, level="ok" if ok else "warning",
                                summary="both layers resilient" if ok else "a layer has an edge-case wedge",
                                observed_at=_iso_now())
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(sentinel_id=self.id, level="unknown", summary=f"unavailable: {exc!r}",
                                observed_at=_iso_now())
