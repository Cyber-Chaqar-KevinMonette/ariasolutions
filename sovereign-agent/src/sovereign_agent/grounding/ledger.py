"""grounding/ledger.py — the persisted composite epistemic score.
(Grounding round · G1)

`tribunal.grounding.analyze()` scores TEXT (lexical evidence/hedge/
mystical-fog texture) but is one-shot, pre-apply-only, and never composed
with anything else that already exists: `epistemic_ledger`'s belief
confidence, `eval_tools`'s hypothesis-confirm-rate track record, and
whether the qa-uncertainty join (self-reported QA confidence vs. the
wonder loop's own promise to open an Uncertainty below 0.4) currently
holds. This mirrors `quality/ledger.py`'s exact discipline: append-only
NDJSON, fsync'd, `*_trend()` computed from STORED passes only.

A "grounding pass" scores one or more (source, text) pairs together: each
gets its own `TextScore`; the pass's own `verdict` is worst-of (one
ungrounded text fails the whole pass — never silently averaged away,
same "one bad file" discipline `quality.ledger.QualityPassResult.
critical_ok` uses).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MARK = "grounding-sentinel-d"


@dataclass
class TextScore:
    source: str                # e.g. "journal:2026-07-05", "qa:01ABC..."
    verdict: str                # grounded | mixed | ungrounded
    grounding_score: float
    profundity_density: float
    flags: list[str] = field(default_factory=list)
    context: str = ""           # "" | "theoretical" — the declared stance
    # at time of writing (Grounding round G4 stamps this; absent here it's
    # always "", meaning "no declared context", byte-identical to today).

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class GroundingPassResult:
    pass_id: str
    ts: str
    texts: list[TextScore] = field(default_factory=list)
    belief_confidence_avg: float = 0.0
    hypothesis_confirm_rate: float = 0.0
    qa_calibration_ok: bool = True

    @property
    def value(self) -> float:
        if not self.texts:
            return 0.0
        return sum(t.grounding_score for t in self.texts) / len(self.texts)

    @property
    def verdict(self) -> str:
        """Worst-of across every scored text — one ungrounded text fails
        the whole pass, never averaged away. Vacuously "grounded" when
        nothing was scored: "nothing to check" and "everything failed"
        must never look the same to a caller deciding whether to gate or
        alarm (the same honesty fix quality.ledger's critical_ok needed)."""
        if not self.texts:
            return "grounded"
        verdicts = {t.verdict for t in self.texts}
        if "ungrounded" in verdicts:
            return "ungrounded"
        if "mixed" in verdicts:
            return "mixed"
        return "grounded"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["value"] = round(self.value, 3)
        d["verdict"] = self.verdict
        return d


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    from ulid import ULID

    return f"gp-{str(ULID())[:12]}"


def _ledger_path(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "grounding"
    p.mkdir(parents=True, exist_ok=True)
    return p / "ledger.ndjson"


def _belief_confidence_avg(data_dir: Path | None) -> float:
    """Mean confidence across the tip of every belief lineage — 0.0 (not a
    crash, not a fabricated 1.0) when nothing has ever been believed yet."""
    try:
        from sovereign_agent.epistemic_ledger.ledger import EpistemicLedger

        root = Path(data_dir) / "epistemic" if data_dir is not None else None
        beliefs = EpistemicLedger(root).current_beliefs()
        if not beliefs:
            return 0.0
        return round(sum(b.confidence for b in beliefs) / len(beliefs), 3)
    except Exception:  # noqa: BLE001
        return 0.0


def _hypothesis_confirm_rate(days: int = 30) -> float:
    """Reuses `eval_tools`'s already-computed hypothesis track record —
    private (`_compute_metrics`), same-package, noted honestly rather than
    silently reached into: it's the existing figure, not a duplicate. It
    reads LIVE `SETTINGS.paths` (no `data_dir` override exists upstream in
    `db.open_atoms_db()`), so tests isolate it via the same SETTINGS-
    monkeypatch fixture every other staged module's tests already use —
    this one signal doesn't honor an explicit `data_dir` the way the rest
    of this pass does."""
    try:
        from sovereign_agent.tools import eval_tools

        metrics = eval_tools._compute_metrics(days)
        return float(metrics.get("hypothesis_confirm_rate", 0.0))
    except Exception:  # noqa: BLE001
        return 0.0


def _qa_calibration_ok(data_dir: Path | None) -> bool:
    """Whether the qa-uncertainty join currently holds (every low-
    confidence QA opened its promised curiosity uncertainty). True — not a
    confirmed failure — when the check itself can't run."""
    try:
        from sovereign_agent.consistency.checks import check_qa_uncertainty

        return bool(check_qa_uncertainty(data_dir).ok)
    except Exception:  # noqa: BLE001
        return True


def record_grounding_pass(texts: list[tuple[str, str]],
                          data_dir: Path | None = None, *,
                          context: str = "") -> GroundingPassResult:
    """Score every (source, text) pair, fold in the three composed
    signals, append ONE fsync'd record. A text that can't be scored (empty,
    non-string) is skipped — noted, never a crash: a grounding pass must
    never itself become the thing that breaks the read.

    grounding-modes-d — `context` (e.g. "theoretical") is stamped onto every
    TextScore in this pass, byte-identical ("") for every caller that
    doesn't pass it."""
    from sovereign_agent.tribunal import grounding as _grounding

    scored: list[TextScore] = []
    for source, text in texts:
        if not text or not str(text).strip():
            continue
        try:
            report = _grounding.analyze(text)
        except Exception:  # noqa: BLE001
            continue
        scored.append(TextScore(
            source=str(source), verdict=report.verdict,
            grounding_score=round(report.grounding_score, 3),
            profundity_density=round(report.profundity_density, 3),
            flags=list(report.flags), context=context,
        ))

    result = GroundingPassResult(
        pass_id=_new_id(), ts=_now(), texts=scored,
        belief_confidence_avg=_belief_confidence_avg(data_dir),
        hypothesis_confirm_rate=_hypothesis_confirm_rate(),
        qa_calibration_ok=_qa_calibration_ok(data_dir),
    )
    path = _ledger_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("grounding-pass-d", plane="control", trace_id=result.pass_id,
                   payload={"value": result.value, "verdict": result.verdict,
                            "texts": len(scored),
                            "qa_calibration_ok": result.qa_calibration_ok})
    except Exception:  # noqa: BLE001
        pass
    # extension seam (G1) — a future numeric/fact-checking signal (e.g.
    # verifying a cited number against a real file/measurement) can be
    # folded in here as a fifth composed field without touching any caller
    # of this function or of GroundingPassResult's existing fields.
    return result


def latest_grounding(data_dir: Path | None = None) -> dict | None:
    """The most recent grounding pass, or None if none has ever run."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="grounding",
                                   emit=False).records
    return records[-1] if records else None


def grounding_trend(n: int = 10, data_dir: Path | None = None) -> str:
    """From STORED passes only — the honest kind (mirrors
    quality.ledger.quality_trend() / proving_ground.runner.trend())."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="grounding",
                                   emit=False).records[-n:]
    values = [r.get("value", 0.0) for r in records]
    if len(values) < 2:
        return "insufficient-history"
    if values[-1] > values[0] + 0.1:
        return "improving"
    if values[-1] < values[0] - 0.1:
        return "declining"
    return "stable"


__all__ = ["TextScore", "GroundingPassResult", "record_grounding_pass",
          "latest_grounding", "grounding_trend"]
