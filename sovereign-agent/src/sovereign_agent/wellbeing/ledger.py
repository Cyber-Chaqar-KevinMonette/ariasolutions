"""wellbeing/ledger.py — the persisted composite value/care/flourishing score.
(Wellbeing round · W1)

Three real subsystems, composed rather than duplicated:
`companion_tools._build_value_report()` (the love/care/seed classification
+ letter grade — computed today, never kept), `stewardship.msims.
ImpactVector` (`is_7g()`/`is_zombie()` — a rich impact engine reachable
only via one manual CLI path), and `foresight.project()` (the existing
carry-forward verdict machinery `spectrum.lenses.steward()` already
reuses). This mirrors `quality/ledger.py`/`grounding/ledger.py`'s exact
discipline: append-only NDJSON, fsync'd, `*_trend()` computed from STORED
passes only.

A "wellbeing pass" scores one session's worth of events (+ an optional
ImpactVector, when a real plan/witness pair produced one) into ONE
composite verdict — worst-of, never averaged away: an is_zombie() True
(false certainty) fails the whole pass regardless of a good letter grade,
the same "one bad signal fails the pass" discipline the prior two ledgers
use, including the same "nothing scored is honest absence, not a
failure" fix.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

MARK = "wellbeing-sentinel-d"


@dataclass
class WellbeingPassResult:
    pass_id: str
    ts: str
    love_grade: str = "D"
    accomplished_count: int = 0
    care_count: int = 0
    seed_count: int = 0
    event_count_analyzed: int = 0
    impact_is7g: float | None = None
    impact_is_zombie: bool = False
    flourishing_verdict: str = ""

    @property
    def verdict(self) -> str:
        """"strained" on any bad signal, "healthy" otherwise. Vacuously
        "healthy" when nothing was analyzed at all (no events, no IV, no
        flourishing check run) — "nothing to check" and "everything
        strained" must never look the same to a caller deciding whether
        to gate or alarm (the same honesty fix the prior two ledgers'
        empty-pass handling needed)."""
        if self.impact_is_zombie:
            return "strained"
        if (self.event_count_analyzed > 0 and self.love_grade == "D"
                and self.accomplished_count == 0 and self.care_count == 0):
            return "strained"
        if self.flourishing_verdict not in ("", "carry-forward"):
            return "strained"
        return "healthy"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict
        return d


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    from ulid import ULID

    return f"wp-{str(ULID())[:12]}"


def _ledger_path(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "wellbeing"
    p.mkdir(parents=True, exist_ok=True)
    return p / "ledger.ndjson"


def record_wellbeing_pass(events: list[dict] | None = None, iv=None,
                          data_dir: Path | None = None, *,
                          custom_summary: str | None = None,
                          decision_text: str | None = None) -> WellbeingPassResult:
    """Score a session's events (+ an optional ImpactVector, + optional
    decision/proposal text) into one composite pass, append ONE fsync'd
    record. A malformed IV is skipped — noted, never a crash: a wellbeing
    pass must never itself become the thing that breaks the read.

    `decision_text` is deliberately separate from the auto-generated
    session summary: `foresight.project()` scores lock-in/reversibility/
    value-signal VOCABULARY in text describing a real decision or
    proposal — running it over a terse retrospective summary like "3
    accomplishments, 1 act of care" is a category error (found live: it
    scored EVERY such summary "reject-for-the-future", since generic
    retrospective prose never mentions reversibility at all). The
    flourishing check only runs when a caller explicitly hands it real
    decision text to project over; absent that, it's honestly skipped —
    not a fabricated verdict from the wrong kind of input."""
    from sovereign_agent.tools.companion_tools import _build_value_report

    events = events or []
    report = _build_value_report(events, custom_summary)

    impact_is7g: float | None = None
    impact_is_zombie = False
    if iv is not None:
        try:
            impact_is7g = round(float(iv.is_7g()), 3)
            impact_is_zombie = bool(iv.is_zombie())
        except Exception:  # noqa: BLE001
            pass

    flourishing_verdict = ""
    if decision_text:
        try:
            from sovereign_agent.foresight import project

            flourishing_verdict = project({"text": decision_text}).verdict
        except Exception:  # noqa: BLE001
            pass

    result = WellbeingPassResult(
        pass_id=_new_id(), ts=_now(),
        love_grade=str(report.get("overall_grade", "D")),
        accomplished_count=len(report.get("accomplished", [])),
        care_count=len(report.get("value_shown", [])),
        seed_count=len(report.get("seeds", [])),
        event_count_analyzed=int(report.get("event_count_analyzed", 0)),
        impact_is7g=impact_is7g, impact_is_zombie=impact_is_zombie,
        flourishing_verdict=flourishing_verdict,
    )
    path = _ledger_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("wellbeing-pass-d", plane="control", trace_id=result.pass_id,
                   payload={"verdict": result.verdict, "love_grade": result.love_grade,
                            "impact_is_zombie": result.impact_is_zombie,
                            "flourishing_verdict": result.flourishing_verdict})
    except Exception:  # noqa: BLE001
        pass
    # extension seam (W1) — a future signal (e.g. a fourth Relational
    # dimension from stewardship.msims, once it exists) can be folded in
    # here as an additional composed field without touching any caller of
    # this function or of WellbeingPassResult's existing fields.
    return result


def latest_wellbeing(data_dir: Path | None = None) -> dict | None:
    """The most recent wellbeing pass, or None if none has ever run."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="wellbeing",
                                   emit=False).records
    return records[-1] if records else None


def wellbeing_trend(n: int = 10, data_dir: Path | None = None) -> str:
    """From STORED passes only — the honest kind (mirrors
    quality.ledger.quality_trend()/grounding.ledger.grounding_trend())."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="wellbeing",
                                   emit=False).records[-n:]
    healthy = [1.0 if r.get("verdict") == "healthy" else 0.0 for r in records]
    if len(healthy) < 2:
        return "insufficient-history"
    if healthy[-1] > healthy[0]:
        return "improving"
    if healthy[-1] < healthy[0]:
        return "declining"
    return "stable"


__all__ = ["WellbeingPassResult", "record_wellbeing_pass", "latest_wellbeing",
          "wellbeing_trend"]
