"""quantum/trust.py — Council Trust Ledger (witnessing: the council earns its standing).

The non-classical layer is advisory. For it to ever earn a higher role, it must build a verifiable
TRACK RECORD: each council consultation's disposition is logged, and later its real outcome is
recorded. Calibration = how often the council's lean matched reality. Trust is earned one verified
output at a time (the witnessing principle, distilled from the_witnessing_system.md).

Storage: data_dir/quantum/council_trust.ndjson (append-only). Pure-Python stdlib.
"""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def _ledger_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "quantum" / "council_trust.ndjson"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _consult_id(question: str, ts: str) -> str:
    return "C-" + hashlib.sha256(f"{question}|{ts}".encode()).hexdigest()[:10]


def log_consult(data_dir: Path, *, question: str, lean: str, disposition: float,
                coherence: float) -> dict:
    """Record a council consultation (outcome unresolved). Returns the entry."""
    ts = _now()
    entry = {
        "consult_id": _consult_id(question, ts),
        "ts": ts,
        "question": question,
        "lean": lean,                 # yes / no / split
        "disposition": round(float(disposition), 4),
        "coherence": round(float(coherence), 4),
        "outcome": None,              # filled later by record_outcome
        "correct": None,
    }
    with _ledger_path(data_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _replay(data_dir: Path) -> dict[str, dict]:
    path = _ledger_path(data_dir)
    state: dict[str, dict] = {}
    if not path.exists():
        return state
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            state[rec["consult_id"]] = {**state.get(rec["consult_id"], {}), **rec}
        except (json.JSONDecodeError, KeyError):
            continue
    return state


def record_outcome(data_dir: Path, *, consult_id: str, outcome: str) -> dict:
    """Resolve a logged consult with the real outcome (yes/no). Appends a resolution record.

    correct = (council lean matched outcome). 'split' leans are scored as half-credit-neutral
    (not counted as right or wrong).
    """
    state = _replay(data_dir)
    if consult_id not in state:
        return {"ok": False, "error": f"not_found: {consult_id}"}
    rec = dict(state[consult_id])
    outcome = outcome.strip().lower()
    if outcome not in ("yes", "no"):
        return {"ok": False, "error": "invalid_outcome: must be yes or no"}
    lean = rec.get("lean")
    correct = None if lean == "split" else (lean == outcome)
    resolution = {
        "consult_id": consult_id,
        "ts": _now(),
        "question": rec.get("question"),
        "lean": lean,
        "disposition": rec.get("disposition"),
        "coherence": rec.get("coherence"),
        "outcome": outcome,
        "correct": correct,
    }
    with _ledger_path(data_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(resolution, ensure_ascii=False) + "\n")
    return {"ok": True, **resolution}


def calibration(data_dir: Path) -> dict:
    """Compute the council's track record: accuracy on resolved consults."""
    state = _replay(data_dir)
    total = len(state)
    resolved = [r for r in state.values() if r.get("outcome") in ("yes", "no")]
    scored = [r for r in resolved if r.get("correct") is not None]
    correct = sum(1 for r in scored if r.get("correct"))
    accuracy = (correct / len(scored)) if scored else None
    # trust band: earns standing only with enough verified, accurate outputs
    if accuracy is None or len(scored) < 5:
        band = "unproven"
    elif accuracy >= 0.75:
        band = "trusted"
    elif accuracy >= 0.55:
        band = "promising"
    else:
        band = "unreliable"
    return {
        "total_consults": total,
        "resolved": len(resolved),
        "scored": len(scored),
        "correct": correct,
        "accuracy": (round(accuracy, 4) if accuracy is not None else None),
        "trust_band": band,
        "note": "The council earns higher roles only by proving accuracy at scale (witnessing).",
    }
