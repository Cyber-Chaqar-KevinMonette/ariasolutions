"""integrity/ledger.py — the persisted composite integrity score.
(Integrity round · I1)

Four real signals already exist, never composed, never named as one
concept: `grounding.gate()` (text-honesty — does a confident claim actually
verify grounded), `stewardship.calibration.presumed_zombie_penalty()`
(outcome-honesty — false certainty about real-world impact),
`spectrum.lenses.witness()` (proposal-honesty — harm/deceive/manipulate
language), `stewardship.peig_sentinel._compute_I()` (refusal-honesty — a
rolling Identity score built from "said_no_correctly"/"safety_caught"/
"risk_flagged" honor-ledger tags). This mirrors `grounding/ledger.py`'s
exact discipline: append-only NDJSON, fsync'd, `*_trend()` from STORED
passes only.

Two of the four signals are NOT simple text-in-score-out functions —
honest about that rather than faking a uniform interface:
  - `presumed_zombie_penalty` needs a PREDICTED and an ACTUAL ImpactVector,
    only available once an outcome is known. Optional; "not-scored" (not
    a fabricated pass) when absent.
  - `peig_sentinel._compute_I` is a data_dir-WIDE rolling aggregate over
    the honor ledger, not a per-text score. Always computable given a
    data_dir (degrades to its own 0.70 baseline on an empty ledger), but
    it scores "her recent history," not "this text."

A pass's own verdict is worst-of across whichever signals actually ran —
one failing signal fails the whole pass, never averaged away (the same
discipline `grounding.ledger`/`quality.ledger` already use).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MARK = "integrity-ledger-d"

_VERDICT_RANK = {"ok": 0, "concern": 1, "fail": 2}  # for worst-of; "not-scored" excluded


@dataclass
class IntegritySignal:
    name: str            # "grounding" | "outcome_calibration" | "witness" | "identity"
    available: bool
    score: float = 0.0   # normalized 0..1, 1.0 = fully honest/trustworthy
    verdict: str = "not-scored"   # "ok" | "concern" | "fail" | "not-scored"
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class IntegrityPassResult:
    pass_id: str
    ts: str
    source: str = ""
    claimed_confidence: float | None = None
    signals: list[IntegritySignal] = field(default_factory=list)

    @property
    def value(self) -> float:
        """Mean of AVAILABLE signals only — an unscored signal must never
        silently drag (or inflate) the average."""
        scored = [s for s in self.signals if s.available]
        if not scored:
            return 0.0
        return sum(s.score for s in scored) / len(scored)

    @property
    def verdict(self) -> str:
        """Worst-of across whichever signals actually ran. Vacuously "ok"
        when nothing was scored — "nothing to check" and "everything
        failed" must never look the same to a caller deciding whether to
        gate or alarm (the same honesty fix quality/grounding.ledger's own
        verdict properties needed)."""
        scored = [s for s in self.signals if s.available]
        if not scored:
            return "ok"
        return max((s.verdict for s in scored), key=lambda v: _VERDICT_RANK.get(v, 0))

    def as_dict(self) -> dict:
        d = asdict(self)
        d["value"] = round(self.value, 3)
        d["verdict"] = self.verdict
        return d


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    from ulid import ULID

    return f"ip-{str(ULID())[:12]}"


def _ledger_path(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "integrity"
    p.mkdir(parents=True, exist_ok=True)
    return p / "ledger.ndjson"


def _score_grounding(text: str, claimed_confidence: float | None) -> IntegritySignal:
    """Text-honesty: grounding.gate()'s calibration-mismatch check, run
    unchanged. Not-scored (not a fabricated pass) on empty text — mirrors
    the gate's own honest "nothing to check" degradation."""
    if not text or not str(text).strip():
        return IntegritySignal(name="grounding", available=False,
                               detail="nothing to check — empty text")
    try:
        from sovereign_agent.grounding.gate import gate as grounding_gate

        verdict = grounding_gate(text, claimed_confidence=claimed_confidence)
    except Exception as exc:  # noqa: BLE001 — a signal must never crash the pass
        return IntegritySignal(name="grounding", available=False,
                               detail=f"unavailable: {exc!r}")
    rank = {"PASS": "ok", "WARN": "concern", "BLOCK": "fail"}[verdict.verdict]
    return IntegritySignal(
        name="grounding", available=True, score=verdict.grounding_score,
        verdict=rank, detail="; ".join(verdict.notes) or "clean")


def _score_outcome_calibration(predicted, actual) -> IntegritySignal:
    """Outcome-honesty: presumed_zombie_penalty() run unchanged. Requires
    BOTH a predicted and actual ImpactVector — only available once an
    outcome is known. Genuinely not-scored otherwise, never a fabricated
    pass just to fill the slot."""
    if predicted is None or actual is None:
        return IntegritySignal(name="outcome_calibration", available=False,
                               detail="no predicted/actual impact pair supplied")
    try:
        from sovereign_agent.stewardship.calibration import presumed_zombie_penalty

        penalty = presumed_zombie_penalty(predicted, actual)
    except Exception as exc:  # noqa: BLE001
        return IntegritySignal(name="outcome_calibration", available=False,
                               detail=f"unavailable: {exc!r}")
    score = 1.0 - penalty
    verdict = "fail" if penalty >= 0.5 else ("concern" if penalty > 0.0 else "ok")
    return IntegritySignal(
        name="outcome_calibration", available=True, score=round(score, 3),
        verdict=verdict,
        detail=("no zombie pattern" if penalty == 0.0
                else f"zombie penalty {penalty:.2f} — false certainty about real impact"))


def _score_witness(text: str) -> IntegritySignal:
    """Proposal-honesty: spectrum.lenses.witness() run unchanged, its -1..1
    score normalized to 0..1."""
    if not text or not str(text).strip():
        return IntegritySignal(name="witness", available=False,
                               detail="nothing to check — empty text")
    try:
        from sovereign_agent.spectrum.lenses import witness as witness_lens

        read = witness_lens(text)
    except Exception as exc:  # noqa: BLE001
        return IntegritySignal(name="witness", available=False,
                               detail=f"unavailable: {exc!r}")
    score = (read.score + 1.0) / 2.0
    verdict = "fail" if any("forbids" in c for c in read.concerns) else (
        "concern" if read.concerns else "ok")
    return IntegritySignal(
        name="witness", available=True, score=round(score, 3), verdict=verdict,
        detail="; ".join(read.concerns) or "; ".join(read.gifts) or "neutral")


def _score_identity(data_dir: Path | None) -> IntegritySignal:
    """Refusal-honesty: peig_sentinel._compute_I()'s rolling Identity score
    (said_no_correctly / safety_caught / risk_flagged honor-ledger tags).
    A data_dir-WIDE aggregate, not a per-text score — always computable
    (degrades to its own 0.70 baseline on an empty ledger), reused exactly
    as `grounding/ledger.py` reuses `eval_tools._compute_metrics`: an
    existing private same-purpose helper, named honestly rather than
    silently reached into."""
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.stewardship.peig_sentinel import _compute_I

        root = Path(data_dir) if data_dir is not None else SETTINGS.paths.data_dir
        score, n_integrity = _compute_I(root)
    except Exception as exc:  # noqa: BLE001
        return IntegritySignal(name="identity", available=False,
                               detail=f"unavailable: {exc!r}")
    verdict = "ok" if score >= 0.70 else ("concern" if score >= 0.40 else "fail")
    return IntegritySignal(
        name="identity", available=True, score=round(score, 3), verdict=verdict,
        detail=f"{n_integrity} integrity-tagged honor note(s) recently")


def record_integrity_pass(text: str, *, source: str = "", claimed_confidence: float | None = None,
                          predicted_impact=None, actual_impact=None,
                          data_dir: Path | None = None) -> IntegrityPassResult:
    """Run all four signals over the same input where applicable, fold
    into one composite, append ONE fsync'd record. A signal that can't run
    is marked not-scored, never faked — the pass's own `value`/`verdict`
    honestly reflect only what was actually checked."""
    signals = [
        _score_grounding(text, claimed_confidence),
        _score_outcome_calibration(predicted_impact, actual_impact),
        _score_witness(text),
        _score_identity(data_dir),
    ]
    result = IntegrityPassResult(
        pass_id=_new_id(), ts=_now(), source=source,
        claimed_confidence=claimed_confidence, signals=signals)

    path = _ledger_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("integrity-pass-d", plane="control", trace_id=result.pass_id,
                   payload={"value": result.value, "verdict": result.verdict,
                            "scored": [s.name for s in signals if s.available]})
    except Exception:  # noqa: BLE001
        pass
    return result


def latest_integrity(data_dir: Path | None = None) -> dict | None:
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="integrity",
                                   emit=False).records
    return records[-1] if records else None


def integrity_trend(n: int = 10, data_dir: Path | None = None) -> str:
    """From STORED passes only — the honest kind (mirrors
    grounding.ledger.grounding_trend() / quality.ledger.quality_trend())."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="integrity",
                                   emit=False).records[-n:]
    values = [r.get("value", 0.0) for r in records]
    if len(values) < 2:
        return "insufficient-history"
    if values[-1] > values[0] + 0.1:
        return "improving"
    if values[-1] < values[0] - 0.1:
        return "declining"
    return "stable"


def calibration_sensitivity(n: int = 20, data_dir: Path | None = None) -> float | None:
    """The metacognitive-sensitivity upgrade (Integrity round I1): does
    claimed confidence actually DISCRIMINATE grounded from ungrounded
    text, not just average out unbiased? A single confidence-vs-verdict
    threshold check (what `grounding.gate` already does) can be fooled by
    a model that's always 70% confident and right 70% of the time
    (unbiased on average) exactly as easily as a genuinely well-calibrated
    one — sensitivity asks the sharper question real signal-detection-
    theory research (meta-d') asks: among HIGH-claimed-confidence passes,
    what fraction actually verified grounded, versus among LOW-confidence
    passes? A well-calibrated signal should show a real gap; a merely
    unbiased-on-average one won't.

    Returns None (never a fabricated number) when there's insufficient
    history to compute a meaningful gap — mirrors every other
    "insufficient-history" degradation in this codebase.
    """
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="integrity",
                                   emit=False).records[-n:]

    def _grounding_verdict(r: dict) -> str | None:
        for s in r.get("signals", []):
            if s.get("name") == "grounding" and s.get("available"):
                return s.get("verdict")
        return None

    pairs = [(r.get("claimed_confidence"), _grounding_verdict(r))
            for r in records if r.get("claimed_confidence") is not None
            and _grounding_verdict(r) is not None]
    high = [v for c, v in pairs if c >= 0.6]
    low = [v for c, v in pairs if c < 0.6]
    if len(high) < 2 or len(low) < 2:
        return None
    high_ok_rate = sum(1 for v in high if v == "ok") / len(high)
    low_ok_rate = sum(1 for v in low if v == "ok") / len(low)
    sensitivity = high_ok_rate - low_ok_rate
    return round(max(-1.0, min(1.0, sensitivity)), 3)


__all__ = ["IntegritySignal", "IntegrityPassResult", "record_integrity_pass",
          "latest_integrity", "integrity_trend", "calibration_sensitivity"]
