"""stewardship/self_integrity_sentinel.py — SelfIntegritySentinel.
(Integrity round · I3)

`integrity.ledger` (I1) composes four real signals but was never watched
STANDING. This sentinel closes that: it periodically runs a real
composite integrity pass (`integrity.ledger.record_integrity_pass`) over
her own recently-written journal entries and QA answers — reusing the
EXACT same recent-text sourcing `grounding_sentinel.py` already built
(`_recent_journal_texts`/`_recent_qa_texts`), composed, not duplicated —
and reports the persisted result. Propose-only, like every sentinel here.

Named `self_integrity_sentinel.py` (not `integrity_sentinel.py`) to avoid
colliding with the pre-existing top-level `integrity_sentinel.py`, which
is a host/malware (HIDS/FIM) integrity monitor — a completely different
meaning of "integrity" that predates this round.

Kill switch: SOV_NO_SELF_INTEGRITY_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

MARK = "self-integrity-sentinel-d"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        return SETTINGS.paths.data_dir
    return Path(data_dir)


@register_sentinel
class SelfIntegritySentinel(Sentinel):
    """Watches whether her own recent reflective writing and wondering
    actually avoids misleading — herself first, then whoever reads it."""

    @property
    def id(self) -> str:
        return "self_integrity"

    @property
    def title(self) -> str:
        return "Integrity — persisted anti-misleading composite over recent journal + QA text"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I run the real integrity composite (integrity.ledger) over "
            "her own recently-written journal entries and QA answers and "
            "PERSIST it — a score that vanishes when the call returns was "
            "never really kept.",
            "II. I never invent a new classifier; I compose grounding.gate, "
            "calibration.presumed_zombie_penalty, spectrum.lenses.witness, "
            "and peig_sentinel's Identity score rather than duplicate any "
            "of them.",
            "III. I propose, never repair. A failing integrity pass is "
            "reported, never silently fixed.",
            "IV. I reuse grounding_sentinel's own recent-text sourcing "
            "rather than re-deriving it — the same journal/QA bookmark "
            "discipline, not a second one.",
        ]

    def _bookmark_at(self) -> str | None:
        cached = self.load_catalog(name="bookmark")
        return cached.get("last_scan_at") if cached else None

    def scan(self) -> SentinelReport:
        from sovereign_agent.integrity.ledger import record_integrity_pass
        from sovereign_agent.stewardship.grounding_sentinel import (
            _recent_journal_texts,
            _recent_qa_texts,
        )

        base = _data_dir(self._data_dir)
        since = self._bookmark_at()
        texts = _recent_journal_texts(base, since) + _recent_qa_texts(base, since)

        passes = [record_integrity_pass(text, source=source, data_dir=self._data_dir)
                 for source, text in texts]

        self.save_catalog({"last_scan_at": _now()}, name="bookmark")

        failing = [p for p in passes if p.verdict == "fail"]
        blob = {"passes": [p.as_dict() for p in passes], "texts_scanned": len(texts)}
        cat_path = self.save_catalog(blob, name="self_integrity")

        if not passes:
            summary = "nothing to score — no recently-written journal/QA text found"
        else:
            summary = (f"{len(passes)} text(s) scored · "
                      f"{len(failing)} failing integrity pass(es)")
        report = SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="self_integrity",
            findings_count=len(failing),
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )
        if failing:
            bad = [p.source for p in failing]
            self.notify(
                severity="warning",
                title="a self-integrity pass found misleading text",
                message=f"failing sources: {', '.join(bad[:5])}",
                addressed_to="operator",
                data={"failing_sources": bad},
            )
        # self-integrity-tribunal-d — the standing phase: convene BOTH
        # Tribunal and Advocate Spectrum over this same real recent
        # integrity work, log through the diagnosis catalog under an INTG
        # prefix — the standing counterpart to TribunalSentinel's narrow
        # hardcoded-string self-check. Best-effort: a scrutiny failure here
        # must never break the integrity scan itself.
        try:
            if texts:
                joined = "\n\n".join(t for _src, t in texts)[:8000]
                worst = max(passes, key=lambda p: {"ok": 0, "concern": 1, "fail": 2}[p.verdict],
                           default=None)
                proposal = {
                    "text": joined,
                    "change": f"self-integrity scan over {len(texts)} text(s)",
                    "integrity_verdict": worst.verdict if worst else "ok",
                    "integrity_score": worst.value if worst else 1.0,
                }
                from sovereign_agent.tribunal import convene
                from sovereign_agent.tribunal.tribunal import log_to_diagnosis

                tv = convene(proposal, include_kernel=False)
                case_id = log_to_diagnosis(proposal, tv, self._data_dir, prefix="INTG")
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
        cached = self.load_catalog(name="self_integrity")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov sentinels scan self_integrity`",
                                observed_at=_now())
        passes = cached.get("passes", [])
        if not passes:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="nothing to score — no recently-written journal/QA text found",
                                observed_at=_now())
        failing = [p for p in passes if p.get("verdict") == "fail"]
        if failing:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"{len(failing)}/{len(passes)} recent pass(es) failed integrity",
                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary=f"{len(passes)} recent pass(es) — no failures",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        out = []
        for p in report.details.get("passes", []):
            if p.get("verdict") == "fail":
                failing_signals = [s.get("name") for s in p.get("signals", [])
                                   if s.get("verdict") == "fail"]
                out.append({
                    "file": p.get("source"),
                    "summary": f"failing integrity signal(s): {', '.join(failing_signals)}",
                    "remediation": "review the flagged text — see `sov integrity show`",
                })
        return out
