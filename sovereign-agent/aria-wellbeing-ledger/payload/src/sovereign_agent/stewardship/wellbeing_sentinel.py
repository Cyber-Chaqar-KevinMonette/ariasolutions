"""stewardship/wellbeing_sentinel.py — WellbeingSentinel. (Wellbeing round · W1)

`companion_tools.value_report()` was a real, callable tool but computed
fresh every call and never kept; `stewardship.msims`'s impact-vector engine
and `stewardship.calibration.honor_score()` were real but reachable only
via one manual CLI path. This sentinel closes the "never watched
standing" half: it periodically runs a real composite wellbeing pass
(`wellbeing.ledger.record_wellbeing_pass`) over recently-emitted events
and reports the persisted result — propose-only, like every sentinel here.

"Recently touched" = events newer than this sentinel's own last-scan
bookmark, falling back to the newest few hundred on a fresh install
(nothing scanned yet).

Kill switch: SOV_NO_WELLBEING_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

MARK = "wellbeing-sentinel-d"
_FRESH_INSTALL_WINDOW = 300


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _recent_events(since_iso: str | None) -> list[dict]:
    """Events since `since_iso`, or the newest window on a fresh install
    (no bookmark yet). [] on any failure — never a crash."""
    try:
        from sovereign_agent.tools.companion_tools import _load_recent_events_for_report

        events = _load_recent_events_for_report(_FRESH_INSTALL_WINDOW)
    except Exception:  # noqa: BLE001
        return []
    if since_iso:
        events = [e for e in events if str(e.get("ts", "")) > since_iso]
    return events


@register_sentinel
class WellbeingSentinel(Sentinel):
    """Watches whether her own recent work is actually showing value and
    care — not just whether the letter grade would be good if asked."""

    @property
    def id(self) -> str:
        return "wellbeing"

    @property
    def title(self) -> str:
        return "Wellbeing — persisted value/care/flourishing score over recent work"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I run the real value-report classifier (companion_tools."
            "_build_value_report) over recently-emitted events and PERSIST "
            "the composite score — a score that vanishes when the call "
            "returns was never really kept.",
            "II. I never invent a new classifier; I compose what already "
            "exists (companion_tools, stewardship.msims, foresight) rather "
            "than duplicate it.",
            "III. I propose, never repair. A strained pass — false "
            "certainty, or a session that produced and showed nothing — "
            "is reported, never silently fixed.",
            "IV. 'Recently touched' means since my own last look, or the "
            "newest few hundred events on a fresh install — never her "
            "entire event history at once.",
        ]

    def _bookmark_at(self) -> str | None:
        cached = self.load_catalog(name="bookmark")
        return cached.get("last_scan_at") if cached else None

    def scan(self) -> SentinelReport:
        from sovereign_agent.wellbeing.ledger import record_wellbeing_pass

        since = self._bookmark_at()
        events = _recent_events(since)
        result = record_wellbeing_pass(events, data_dir=self._data_dir)

        self.save_catalog({"last_scan_at": _now()}, name="bookmark")

        blob = {"pass": result.as_dict(), "events_scanned": len(events)}
        cat_path = self.save_catalog(blob, name="wellbeing")
        if not events:
            summary = "nothing to score — no recent events found"
        else:
            summary = (f"{len(events)} event(s) scored · verdict={result.verdict} "
                      f"· grade={result.love_grade}")
            if result.impact_is_zombie:
                summary += " · zombie signal (false certainty)"
        report = SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="wellbeing",
            findings_count=1 if events and result.verdict == "strained" else 0,
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )
        if events and result.verdict == "strained":
            self.notify(
                severity="warning",
                title="a wellbeing pass came back strained",
                message=(f"grade={result.love_grade}, accomplished="
                        f"{result.accomplished_count}, care={result.care_count}"
                        + (", zombie signal" if result.impact_is_zombie else "")
                        + (f", flourishing={result.flourishing_verdict}"
                           if result.flourishing_verdict not in ("", "carry-forward")
                           else "")),
                addressed_to="operator",
                data={"verdict": result.verdict, "love_grade": result.love_grade},
            )
        # {MARK} — extension seam: W3 (aria-wellbeing-tribunal) hooks a
        # second standing-audit phase HERE, convening Tribunal + Advocate
        # Spectrum over this same real recent wellbeing pass, logged through
        # diagnosis.ConflictCatalog under type="ambiguity" prefix="WELL" —
        # mirrors quality_sentinel.py's/grounding_sentinel.py's own seams
        # and Q3's/G3's use of them exactly.
        return report

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="wellbeing")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov sentinels scan wellbeing`",
                                observed_at=_now())
        pass_data = cached.get("pass", {})
        verdict = pass_data.get("verdict", "healthy")
        events_scanned = cached.get("events_scanned", 0)
        if not events_scanned:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="nothing to score — no recent events found",
                                observed_at=_now())
        if verdict == "strained":
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"wellbeing verdict=strained in last pass "
                        f"(grade={pass_data.get('love_grade', '?')})",
                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary=f"wellbeing verdict=healthy "
                                    f"(grade={pass_data.get('love_grade', '?')})",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        out = []
        pass_data = report.details.get("pass", {})
        if pass_data.get("verdict") == "strained":
            out.append({
                "file": "wellbeing",
                "summary": f"strained wellbeing pass: grade={pass_data.get('love_grade')}, "
                          f"accomplished={pass_data.get('accomplished_count')}, "
                          f"care={pass_data.get('care_count')}",
                "remediation": "reflect on what could be done differently — "
                              "see `sov wellbeing show` for the full breakdown",
            })
        return out
