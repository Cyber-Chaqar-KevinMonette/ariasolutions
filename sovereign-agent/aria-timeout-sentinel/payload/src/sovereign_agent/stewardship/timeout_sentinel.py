"""stewardship/timeout_sentinel.py — TimeoutSentinel. (Timeout round · T3)

`timeouts.ledger` (T1) composes a real classification but was never
watched STANDING. This sentinel closes that: it periodically runs
`timeouts.ledger.record_timeout_scan()` over recent events and reports
the persisted result — propose-only, like every sentinel here. Only
NEWLY-appeared unexplained timeouts since its own last look trigger a
notification; the scan itself always covers the recent window (T1's own
design), but repeatedly re-alarming on an already-seen timeout the
operator has already been told about would just be noise.

Kill switch: SOV_NO_TIMEOUT_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

MARK = "timeout-sentinel-d"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        return SETTINGS.paths.data_dir
    return Path(data_dir)


@register_sentinel
class TimeoutSentinel(Sentinel):
    """Watches whether her own recent timeouts are actually explained —
    a bounded, catalogued wait, not an unexplained hang recurring quietly."""

    @property
    def id(self) -> str:
        return "timeout"

    @property
    def title(self) -> str:
        return "Timeout — persisted justified/unexplained classification over recent events"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I run the real timeout classifier (timeouts.ledger) over "
            "recent events and PERSIST the composite result — a "
            "classification that vanishes when the call returns was "
            "never really kept.",
            "II. I never invent a new classifier; I compose "
            "TIMEOUT_CATALOG's known-bounded sites rather than duplicate "
            "the judgment call elsewhere.",
            "III. I propose, never repair. An unexplained timeout is "
            "reported, never silently retried or suppressed.",
            "IV. 'Newly appeared' means since my own last look — I don't "
            "re-alarm on the same already-reported timeout every scan.",
        ]

    def _bookmark_at(self) -> str | None:
        cached = self.load_catalog(name="bookmark")
        return cached.get("last_scan_at") if cached else None

    def scan(self) -> SentinelReport:
        from sovereign_agent.timeouts.ledger import record_timeout_scan

        since = self._bookmark_at()
        result = record_timeout_scan(self._data_dir)

        new_unexplained = [e for e in result.events
                          if e.verdict == "unexplained" and (since is None or e.ts > since)]

        self.save_catalog({"last_scan_at": _now()}, name="bookmark")

        blob = {"scan": result.as_dict(), "new_unexplained_count": len(new_unexplained)}
        cat_path = self.save_catalog(blob, name="timeout")

        if not result.events:
            summary = "nothing to score — no timeout events found"
        else:
            summary = (f"{len(result.events)} timeout event(s) scanned · "
                      f"{len(new_unexplained)} newly-unexplained")
        report = SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="timeout",
            findings_count=len(new_unexplained),
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )
        if new_unexplained:
            bad = [f"{e.tool} ({e.flag}, {e.timeout_seconds}s)" for e in new_unexplained]
            self.notify(
                severity="warning",
                title="an unexplained timeout appeared",
                message=f"newly-unexplained: {', '.join(bad[:5])}",
                addressed_to="operator",
                data={"unexplained": bad},
            )
        # timeout-tribunal-d — the standing phase: convene BOTH Tribunal
        # and Advocate Spectrum over this same real recent timeout scan,
        # log through the diagnosis catalog — the standing counterpart to
        # TribunalSentinel's narrow hardcoded-string self-check.
        # Best-effort: a scrutiny failure here must never break the scan.
        try:
            if new_unexplained:
                proposal = {
                    "text": f"timeout scan {result.scan_id}: "
                           f"{len(new_unexplained)} newly-unexplained timeout(s)",
                    "change": f"timeout scan {result.scan_id}",
                    "unexplained_count": len(new_unexplained),
                }
                from sovereign_agent.tribunal import convene
                from sovereign_agent.tribunal.tribunal import log_to_diagnosis

                tv = convene(proposal, include_kernel=False)
                case_id = log_to_diagnosis(proposal, tv, self._data_dir, prefix="TMOT")
                standing = {"verdict": tv.verdict, "case_id": case_id}
                try:
                    from sovereign_agent.spectrum import convene_spectrum

                    cv = convene_spectrum(proposal)
                    standing["spectrum_verdict"] = cv.verdict
                    standing["spectrum_opposed"] = cv.opposed
                except Exception:  # noqa: BLE001 — spectrum is optional
                    pass
                self.save_catalog(standing, name="standing-audit")
        except Exception:  # noqa: BLE001 — a scrutiny failure never breaks the scan
            pass
        return report

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="timeout")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov sentinels scan timeout`",
                                observed_at=_now())
        scan = cached.get("scan", {})
        if not scan.get("events"):
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="nothing to score — no timeout events found",
                                observed_at=_now())
        if cached.get("new_unexplained_count", 0):
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"{cached['new_unexplained_count']} newly-unexplained timeout(s) in last scan",
                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary=f"{len(scan.get('events', []))} timeout event(s) — all justified",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        out = []
        for e in report.details.get("scan", {}).get("events", []):
            if e.get("verdict") == "unexplained":
                out.append({
                    "file": e.get("tool") or e.get("flag"),
                    "summary": f"unexplained timeout: {e.get('flag')} ({e.get('timeout_seconds')}s, "
                              f"catalogued bound {e.get('catalogued_bound')})",
                    "remediation": "either add this source to TIMEOUT_CATALOG with its "
                                  "real bound, or investigate why it exceeded it",
                })
        return out
