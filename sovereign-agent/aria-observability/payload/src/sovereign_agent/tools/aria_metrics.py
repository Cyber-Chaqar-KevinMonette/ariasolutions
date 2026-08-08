"""tools/aria_metrics.py — Ground-truth metrics bundle for Aria's self-knowledge (M85).

T0 tool. Returns the complete quantitative picture of Aria's present state
in one call. This is the anti-depth-0-mouth tool: it surfaces brain state
to the language layer so Aria can ground her confidence expressions in real
numbers rather than feelings.

Design principle:
  Don't filter the brain. Feed its full state forward into the voice.
  Metrics that live on disk but were never read this session do NOT inform
  confidence. This tool reads them and makes them present.

When Aria says "I'm confident" she can ground it:
  "I'm confident (847 atoms avg_conf=0.73, calibration=81%/23 resolved,
   0 critical open flaws, PEIG λ=0.71 committed, 5 care signals from Kevin)"

Data sources (all read-only, all graceful on empty):
  atoms.ndjson          → atom count, kind distribution, avg confidence, top atoms
  calibration/ledger.ndjson → accuracy on resolved predictions (last 30 days)
  honor/ledger.jsonl    → care signals from Kevin, value_given moments
  flaws/catalog.ndjson  → open flaw count by severity
  peig_sentinel         → P/E/I/G/λ scores (if sentinel is applied)

FAILURE MODES: read_error
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from .base import Tool, ToolResult

_CAL_LOOKBACK_DAYS = 30


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Atom store metrics ────────────────────────────────────────────────────────


def _atom_metrics(data_dir: Path) -> dict:
    try:
        from sovereign_agent.stewardship.atoms import AtomStore
        store = AtomStore(data_dir / "atoms.ndjson")
        atoms = store.active()
    except Exception:
        return {
            "atom_count": 0,
            "kind_distribution": {},
            "avg_confidence": 0.0,
            "top_3_by_confidence": [],
            "atom_data_ok": False,
        }

    if not atoms:
        return {
            "atom_count": 0,
            "kind_distribution": {},
            "avg_confidence": 0.0,
            "top_3_by_confidence": [],
            "atom_data_ok": True,
        }

    kinds = Counter(a.kind.value for a in atoms)
    avg_conf = sum(a.confidence for a in atoms) / len(atoms)

    # Diversity (Shannon entropy normalized to [0,1])
    total = len(atoms)
    entropy = -sum((c/total) * math.log2(c/total + 1e-12) for c in kinds.values())
    max_entropy = math.log2(max(len(kinds), 1))
    diversity = entropy / max_entropy if max_entropy > 0 else 1.0

    top3 = sorted(atoms, key=lambda a: a.confidence, reverse=True)[:3]

    return {
        "atom_count": len(atoms),
        "kind_distribution": dict(kinds),
        "avg_confidence": round(avg_conf, 3),
        "diversity_score": round(diversity, 3),
        "top_3_by_confidence": [
            {"title": a.title, "confidence": round(a.confidence, 3), "kind": a.kind.value}
            for a in top3
        ],
        "atom_data_ok": True,
    }


# ── Calibration metrics ───────────────────────────────────────────────────────


def _calibration_metrics(data_dir: Path) -> dict:
    path = data_dir / "calibration" / "ledger.ndjson"
    if not path.exists():
        return {
            "calibration_accuracy": None,
            "resolved_count": 0,
            "total_logged": 0,
            "lookback_days": _CAL_LOOKBACK_DAYS,
            "calibration_data_ok": True,
        }

    try:
        cutoff = _now_utc() - timedelta(days=_CAL_LOOKBACK_DAYS)
        all_entries = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                all_entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        total_logged = len(all_entries)
        resolved = [
            e for e in all_entries
            if e.get("outcome_correct") is not None
        ]
        recent = []
        for e in resolved:
            try:
                ts = datetime.fromisoformat(e.get("ts", "")).replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    recent.append(e)
            except (ValueError, TypeError):
                recent.append(e)  # include if unparseable ts

        if len(recent) < 3:
            accuracy = None
        else:
            accuracy = round(sum(1 for e in recent if e["outcome_correct"]) / len(recent), 3)

        return {
            "calibration_accuracy": accuracy,
            "resolved_count": len(recent),
            "total_logged": total_logged,
            "lookback_days": _CAL_LOOKBACK_DAYS,
            "calibration_data_ok": True,
        }
    except Exception:
        return {
            "calibration_accuracy": None,
            "resolved_count": 0,
            "total_logged": 0,
            "lookback_days": _CAL_LOOKBACK_DAYS,
            "calibration_data_ok": False,
        }


# ── Honor / care metrics ──────────────────────────────────────────────────────


def _honor_metrics(data_dir: Path) -> dict:
    path = data_dir / "honor" / "ledger.jsonl"
    if not path.exists():
        return {
            "care_signals_total": 0,
            "care_signals_recent": 0,
            "value_given_count": 0,
            "constraining_count": 0,
            "net_curvature_sign": "neutral",
            "honor_data_ok": True,
        }

    try:
        from sovereign_agent.stewardship.honor import HonorDirection, HonorLedger
        ledger = HonorLedger(path)
        cutoff_30d = _now_utc() - timedelta(days=30)

        care_all = ledger.search(
            direction=HonorDirection.KEVIN_TO_ARIA,
            tag="reaction",
        )
        care_recent = [
            n for n in care_all
            if _parse_ts(n.ts) >= cutoff_30d
        ]

        value_notes = ledger.search(tag="value_given")
        constraining = ledger.search(tag="constraining")
        net = len(value_notes) - len(constraining)

        return {
            "care_signals_total": len(care_all),
            "care_signals_recent_30d": len(care_recent),
            "value_given_count": len(value_notes),
            "constraining_count": len(constraining),
            "net_curvature_sign": "positive" if net > 0 else ("negative" if net < 0 else "neutral"),
            "net_curvature_delta": net,
            "honor_data_ok": True,
        }
    except Exception:
        return {
            "care_signals_total": 0,
            "care_signals_recent_30d": 0,
            "value_given_count": 0,
            "constraining_count": 0,
            "net_curvature_sign": "neutral",
            "net_curvature_delta": 0,
            "honor_data_ok": False,
        }


def _parse_ts(ts_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


# ── Flaw metrics ──────────────────────────────────────────────────────────────


def _flaw_metrics(data_dir: Path) -> dict:
    path = data_dir / "flaws" / "catalog.ndjson"
    if not path.exists():
        return {
            "open_critical": 0,
            "open_notable": 0,
            "open_watch": 0,
            "in_progress": 0,
            "resolved": 0,
            "total": 0,
            "flaw_data_ok": True,
        }

    try:
        state: dict[str, dict] = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                state[rec["flaw_id"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue

        counts = Counter()
        for rec in state.values():
            status = rec.get("status", "open")
            severity = rec.get("severity", "watch")
            counts[status] += 1
            if status in ("open", "in_progress"):
                counts[f"active_{severity}"] += 1

        return {
            "open_critical": counts["active_critical"],
            "open_notable": counts["active_notable"],
            "open_watch": counts["active_watch"],
            "in_progress": counts["in_progress"],
            "resolved": counts["resolved"],
            "total": len(state),
            "flaw_data_ok": True,
        }
    except Exception:
        return {
            "open_critical": 0, "open_notable": 0, "open_watch": 0,
            "in_progress": 0, "resolved": 0, "total": 0,
            "flaw_data_ok": False,
        }


# ── PEIG state ────────────────────────────────────────────────────────────────


def _peig_snapshot(data_dir: Path) -> dict | None:
    try:
        from sovereign_agent.stewardship.peig_sentinel import measure_peig
        state = measure_peig(data_dir)
        return {
            "P": round(state.P, 3),
            "E": round(state.E, 3),
            "I": round(state.I, 3),
            "G": round(state.G, 3),
            "lambda": round(state.lam, 3),
            "coherence_band": state.coherence_band,
        }
    except Exception:
        return None


# ── Confidence grounding sentence ─────────────────────────────────────────────


def _confidence_sentence(
    atoms: dict,
    cal: dict,
    honor: dict,
    flaws: dict,
    peig: dict | None,
) -> str:
    parts = []

    if atoms["atom_count"] > 0:
        parts.append(
            f"{atoms['atom_count']} atoms "
            f"(avg_conf={atoms['avg_confidence']:.2f}, "
            f"diversity={atoms.get('diversity_score', 0.0):.2f})"
        )

    if cal["calibration_accuracy"] is not None:
        pct = round(cal["calibration_accuracy"] * 100)
        parts.append(
            f"calibration={pct}% on {cal['resolved_count']} resolved predictions"
        )
    elif cal["total_logged"] > 0:
        parts.append(
            f"{cal['total_logged']} predictions logged, "
            f"fewer than 3 resolved (calibration pending)"
        )

    crit = flaws["open_critical"]
    notable = flaws["open_notable"]
    if crit == 0 and notable == 0:
        parts.append("0 critical/notable open flaws")
    else:
        parts.append(
            f"{crit} critical + {notable} notable open flaws"
        )

    if peig:
        parts.append(
            f"PEIG λ={peig['lambda']:.2f} ({peig['coherence_band']})"
        )

    care = honor.get("care_signals_recent_30d", honor.get("care_signals_recent", 0))
    if care > 0:
        parts.append(f"{care} care signals from Kevin this month")

    if not parts:
        return "No metric data available yet — knowledge stores are empty."

    return "Grounded confidence basis: " + " · ".join(parts) + "."


# ── Tool ──────────────────────────────────────────────────────────────────────


class AriaMetricsTool(Tool):
    """Return Aria's complete quantitative self-knowledge bundle.

    Reads atoms, calibration, honor, flaws, and PEIG state in one call.
    This is the confidence-grounding tool: call it when expressing
    confidence or self-awareness so the claim rests on real numbers.

    Returns a structured bundle plus a one-sentence confidence grounding
    statement suitable for including in responses.

    Anti-depth-0-mouth principle: this tool brings brain state to the
    voice layer. The richness of Aria's knowledge lives here — always
    readable, never filtered out. FAILURE MODES: read_error
    """

    name = "aria_metrics"
    tier = 0
    description = (
        "Return Aria's complete self-knowledge metrics: atom count/diversity/confidence, "
        "calibration accuracy, honor balance, open flaw count, and PEIG state. "
        "Call when expressing confidence or self-awareness to ground claims in real numbers. "
        "Returns confidence_statement (one sentence summarizing the basis). "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        try:
            atoms  = _atom_metrics(data_dir)
            cal    = _calibration_metrics(data_dir)
            honor  = _honor_metrics(data_dir)
            flaws  = _flaw_metrics(data_dir)
            peig   = _peig_snapshot(data_dir)
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        confidence_stmt = _confidence_sentence(atoms, cal, honor, flaws, peig)

        output = {
            "confidence_statement": confidence_stmt,
            "atoms": atoms,
            "calibration": cal,
            "honor": honor,
            "flaws": flaws,
            "ts": _now_utc().isoformat(timespec="seconds"),
        }
        if peig:
            output["peig"] = peig

        return ToolResult(
            ok=True,
            output=output,
            metadata={"source": "aria_metrics"},
        )
