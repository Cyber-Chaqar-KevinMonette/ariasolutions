"""stewardship/grounding_sentinel.py — GroundingSentinel. (Grounding round · G1)

`tribunal/grounding.py` + `epistemic_ledger` + `curiosity.py`'s wonder loop
were each real but never composed and never watched STANDING. This
sentinel closes that: it periodically runs a real composite grounding
pass (`grounding.ledger.record_grounding_pass`) over her own recently-
written journal entries and QA answers, and reports the persisted result
— propose-only, like every sentinel here.

"Recently touched" = journal files (`journal/*.md`, not git-tracked, so
this bookmarks by mtime rather than git-diff) and QA records
(`qa/qa.ndjson`) newer than this sentinel's own last scan, falling back to
the newest few of each on a fresh install (nothing scanned yet).

Kill switch: SOV_NO_GROUNDING_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

MARK = "grounding-sentinel-d"
_FRESH_INSTALL_JOURNAL_N = 3
_FRESH_INSTALL_QA_N = 5


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        return SETTINGS.paths.data_dir
    return Path(data_dir)


def _recent_journal_texts(data_dir: Path, since_iso: str | None) -> list[tuple[str, str]]:
    """(source, text) pairs from journal/*.md newer than `since_iso` (mtime-
    based — journal/ isn't git-tracked). Falls back to the newest few files
    on a fresh install (no bookmark yet)."""
    journal_dir = data_dir / "journal"
    if not journal_dir.is_dir():
        return []
    files = sorted(journal_dir.glob("*.md"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    if since_iso:
        since_ts = datetime.fromisoformat(since_iso.replace("Z", "+00:00")).timestamp()
        files = [f for f in files if f.stat().st_mtime > since_ts]
    else:
        files = files[:_FRESH_INSTALL_JOURNAL_N]
    out = []
    for f in files:
        try:
            out.append((f"journal:{f.stem}", f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return out


def _recent_qa_texts(data_dir: Path, since_iso: str | None) -> list[tuple[str, str]]:
    """(source, text) pairs from qa/qa.ndjson newer than `since_iso`. Falls
    back to the newest few records on a fresh install."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    qa_path = data_dir / "qa" / "qa.ndjson"
    records = read_ndjson_tolerant(qa_path, store="qa", emit=False).records
    if since_iso:
        records = [r for r in records if str(r.get("asked_at", "")) > since_iso]
    else:
        records = records[-_FRESH_INSTALL_QA_N:]
    return [(f"qa:{r.get('qa_id', '?')}", str(r.get("answer", ""))) for r in records
           if r.get("answer")]


@register_sentinel
class GroundingSentinel(Sentinel):
    """Watches whether her own recent reflective writing and wondering
    actually holds up — not just whether it reads well."""

    @property
    def id(self) -> str:
        return "grounding"

    @property
    def title(self) -> str:
        return "Grounding — persisted epistemic score over recent journal + QA text"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I run the real grounding classifier (tribunal.grounding) "
            "over her own recently-written journal entries and QA answers "
            "and PERSIST the composite score — a score that vanishes when "
            "the call returns was never really kept.",
            "II. I never invent a new classifier; I compose what already "
            "exists (tribunal.grounding, epistemic_ledger, eval_tools's "
            "hypothesis track record, the qa-uncertainty join) rather than "
            "duplicate it.",
            "III. I propose, never repair. An ungrounded pass or a broken "
            "confidence calibration is reported, never silently fixed.",
            "IV. 'Recently touched' means since my own last look, or the "
            "newest few journal/QA records on a fresh install — never every "
            "entry she's ever written at once.",
        ]

    def _bookmark_at(self) -> str | None:
        cached = self.load_catalog(name="bookmark")
        return cached.get("last_scan_at") if cached else None

    def scan(self) -> SentinelReport:
        from sovereign_agent.grounding.ledger import record_grounding_pass

        base = _data_dir(self._data_dir)
        since = self._bookmark_at()

        texts = _recent_journal_texts(base, since) + _recent_qa_texts(base, since)
        result = record_grounding_pass(texts, self._data_dir)

        self.save_catalog({"last_scan_at": _now()}, name="bookmark")

        blob = {"pass": result.as_dict(), "texts_scanned": len(texts)}
        cat_path = self.save_catalog(blob, name="grounding")
        if not result.texts:
            summary = "nothing to score — no recently-written journal/QA text found"
        else:
            summary = (f"{len(result.texts)} text(s) scored · verdict={result.verdict} "
                      + (f"· {result.value:.2f} grounding score"))
            if not result.qa_calibration_ok:
                summary += " · calibration join broken"
        report = SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="grounding",
            findings_count=len([t for t in result.texts if t.verdict == "ungrounded"]),
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )
        if result.texts and (result.verdict == "ungrounded" or not result.qa_calibration_ok):
            bad = [t.source for t in result.texts if t.verdict == "ungrounded"]
            self.notify(
                severity="warning",
                title="a grounding pass found ungrounded text or a broken calibration join",
                message=(f"verdict={result.verdict}"
                        + (f"; ungrounded: {', '.join(bad[:5])}" if bad else "")
                        + ("" if result.qa_calibration_ok else "; qa-uncertainty join broken")),
                addressed_to="operator",
                data={"ungrounded": bad, "qa_calibration_ok": result.qa_calibration_ok},
            )
        # {MARK} — extension seam: G3 (aria-grounding-tribunal) hooks a
        # second standing-audit phase HERE, convening Tribunal + Advocate
        # Spectrum over this same real recent grounding pass, logged through
        # diagnosis.ConflictCatalog under type="ambiguity" prefix="GRND" —
        # mirrors quality_sentinel.py's own seam and Q3's use of it exactly.
        return report

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="grounding")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov sentinels scan grounding`",
                                observed_at=_now())
        pass_data = cached.get("pass", {})
        texts = pass_data.get("texts", [])
        verdict = pass_data.get("verdict", "grounded")
        qa_ok = pass_data.get("qa_calibration_ok", True)
        if not texts:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="nothing to score — no recently-written journal/QA text found",
                                observed_at=_now())
        if verdict == "ungrounded" or not qa_ok:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"grounding verdict={verdict} in last pass"
                        + ("" if qa_ok else "; qa-uncertainty join broken"),
                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary=f"grounding verdict={verdict} — no critical failures",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        out = []
        for t in report.details.get("pass", {}).get("texts", []):
            if t.get("verdict") == "ungrounded":
                out.append({
                    "file": t.get("source"),
                    "summary": f"ungrounded text: {', '.join(t.get('flags', [])[:2])}",
                    "remediation": "anchor claims in evidence or mark them a "
                                  "falsifiable hypothesis — see `sov grounding show`",
                })
        return out
