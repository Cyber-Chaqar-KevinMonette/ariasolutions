"""security/improvement_gov.py — Self-Improvement Governance Ledger (the meta-layer).

Distilled from Plans/PlanExaminV1.md #891–900 (self-improvement of self-improvement) + the EXPAI
seed-growth pattern: a change is PROMOTED only if vindicated by real-task evidence, DISMISSED if
falsified. Every Ring-2 improvement is logged with what changed, its evidence gate, reversibility, a
rate-governance check (slow down if changes are too rapid), and a plain-language changelog (transparency).

This is what makes Aria not just better, but WISE — she gets better at getting better, transparently,
without ever outpacing human understanding. Append-only ledger; pure-Python.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Rate governance: if more than this many promotions happen within the window, flag for review.
_RATE_WINDOW_HOURS = 24
_RATE_MAX_PROMOTIONS = 12


def _ledger_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "constitution" / "improvement_ledger.ndjson"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> datetime:
    return datetime.now(timezone.utc)


def propose_improvement(data_dir: Path, *, change: str, ring: str, reversible: bool,
                        evidence: str, vindicated: bool, changelog: str) -> dict:
    """Log a proposed/applied Ring-2 self-improvement with its evidence gate (EXPAI).

    A change is PROMOTED only if `vindicated` (passed real-task evidence) AND reversible AND ring-2.
    Otherwise it is DISMISSED (logged for the record, but not promoted).
    """
    ring = ring.strip().lower()
    promotable = bool(vindicated) and bool(reversible) and ("ring-2" in ring or "adaptive" in ring or ring == "ring_2" or ring == "adaptive-mantle")
    decision = "promoted" if promotable else "dismissed"
    reason = []
    if not vindicated:
        reason.append("evidence gate not passed (not vindicated by real-task evidence)")
    if not reversible:
        reason.append("not reversible")
    if not ("ring-2" in ring or "adaptive" in ring or ring in ("ring_2", "adaptive-mantle")):
        reason.append("not a Ring-2 (adaptive-mantle) change — needs the proper ring's gate")

    entry = {
        "ts": _now().isoformat(timespec="seconds"),
        "change": change,
        "ring": ring,
        "reversible": bool(reversible),
        "evidence": evidence,
        "vindicated": bool(vindicated),
        "decision": decision,
        "reason": "; ".join(reason) if reason else "evidence-vindicated, reversible, Ring-2",
        "changelog": changelog,
    }
    with _ledger_path(data_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    rate = _rate_check(data_dir)
    return {**entry, "rate_governance": rate}


def _entries(data_dir: Path) -> list[dict]:
    p = _ledger_path(data_dir)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _rate_check(data_dir: Path) -> dict:
    """Rate governance (#900): flag if promotions are happening too fast (auto-slow-down signal)."""
    cutoff = _now() - timedelta(hours=_RATE_WINDOW_HOURS)
    recent = 0
    for e in _entries(data_dir):
        if e.get("decision") != "promoted":
            continue
        try:
            ts = datetime.fromisoformat(e["ts"])
        except Exception:  # noqa: BLE001
            continue
        if ts >= cutoff:
            recent += 1
    too_fast = recent > _RATE_MAX_PROMOTIONS
    return {
        "promotions_last_24h": recent,
        "limit": _RATE_MAX_PROMOTIONS,
        "too_fast": too_fast,
        "guidance": ("Change rate exceeds the governance limit — SLOW DOWN and let the operator review. "
                     "She must never outpace human understanding of what she's becoming." if too_fast else
                     "Change rate within healthy governance bounds."),
    }


def transparency_report(data_dir: Path, limit: int = 20) -> dict:
    """A plain-language changelog of recent self-improvements (#899 transparency)."""
    entries = _entries(data_dir)
    promoted = [e for e in entries if e.get("decision") == "promoted"]
    dismissed = [e for e in entries if e.get("decision") == "dismissed"]
    return {
        "total_logged": len(entries),
        "promoted": len(promoted),
        "dismissed": len(dismissed),
        "recent_changelog": [
            {"ts": e["ts"], "decision": e["decision"], "change": e["change"], "changelog": e.get("changelog", "")}
            for e in entries[-limit:]
        ],
        "rate_governance": _rate_check(data_dir),
        "note": "Every self-improvement is logged + evidence-gated. Promoted only if vindicated; dismissed if falsified.",
    }
