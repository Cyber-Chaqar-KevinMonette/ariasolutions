"""tools/impulse_tools.py — Institutional Impulse calibration tools (M66).

  institutional_impulse_check()   T0 — three-gate readiness assessment
  wedge_calibrator()              T0 — discover the problem domain to give freely in
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── DB helpers ───────────────────────────────────────────────────────────────


def _count_external_proof_atoms() -> int:
    """Count proof-of-value atoms where person_is_builder is False."""
    if open_atoms_db is None:
        return 0
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref FROM atoms "
            "WHERE type='proof-of-value' AND superseded_at IS NULL",
        ).fetchall()
        conn.close()
        count = 0
        for (content_ref,) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else (content_ref or {})
                content = json.loads(cr.get("content", "{}")) if isinstance(cr.get("content"), str) else cr.get("content", {})
                if not content.get("person_is_builder", True):
                    count += 1
            except Exception:  # noqa: BLE001
                pass
        return count
    except Exception:  # noqa: BLE001
        return 0


def _avg_surprise_level_last_30() -> float:
    """Average surprise_level from last 30 experience atoms."""
    if open_atoms_db is None:
        return 0.0
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref FROM atoms "
            "WHERE type='experience' AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT 30",
        ).fetchall()
        conn.close()
        levels = []
        for (content_ref,) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else (content_ref or {})
                content_str = cr.get("content", "{}")
                content = json.loads(content_str) if isinstance(content_str, str) else (content_str or {})
                level = content.get("surprise_level")
                if isinstance(level, (int, float)):
                    levels.append(float(level))
            except Exception:  # noqa: BLE001
                pass
        return sum(levels) / len(levels) if levels else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _get_experience_atoms_by_domain(days: int) -> dict[str, list[float]]:
    """Return {domain: [surprise_level, ...]} for experience atoms in last N days."""
    if open_atoms_db is None:
        return {}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref FROM atoms "
            "WHERE type='experience' AND superseded_at IS NULL "
            "AND created_at >= ?",
            (cutoff,),
        ).fetchall()
        conn.close()
        domains: dict[str, list[float]] = {}
        for (content_ref,) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else (content_ref or {})
                content_str = cr.get("content", "{}")
                content = json.loads(content_str) if isinstance(content_str, str) else (content_str or {})
                domain = content.get("domain", "general")
                surprise = float(content.get("surprise_level", 0.1))
                domains.setdefault(domain, []).append(surprise)
            except Exception:  # noqa: BLE001
                pass
        return domains
    except Exception:  # noqa: BLE001
        return {}


# ── InstitutionalImpulseCheckTool ────────────────────────────────────────────


class _CheckArgs(BaseModel):
    pass


class InstitutionalImpulseCheckTool(Tool[_CheckArgs]):
    name = "institutional_impulse_check"
    tier = 0
    description = (
        "Run the three-gate maturity check for the institutional impulse: "
        "Proof Gate (witnessed external value), Signal Gate (curiosity not fear), "
        "Generation Gate (7th-gen question — always pending human judgment). "
        "Returns readiness assessment: NOT_READY | PARTIAL | READY. "
        "Call monthly or before any institutional move (platform, scale, etc.)."
    )
    failure_modes = ("db_unavailable",)
    Args = _CheckArgs

    async def execute(self, args: _CheckArgs, *, trace_id: str) -> ToolResult:
        try:
            external_count = await asyncio.to_thread(_count_external_proof_atoms)
            avg_surprise = await asyncio.to_thread(_avg_surprise_level_last_30)
        except Exception as e:  # noqa: BLE001
            external_count = 0
            avg_surprise = 0.0

        # PROOF GATE: external proof count >= 1
        proof_gate_open = external_count < 1
        proof_gate = {
            "status": "open" if proof_gate_open else "green",
            "proof_count": external_count,
            "needed": 1,
            "note": (
                "Find 1 real external user and solve 1 real problem for them (unprompted)."
                if proof_gate_open
                else f"{external_count} external proof instance(s) on record."
            ),
        }

        # SIGNAL GATE: avg surprise_level > 0.4 → curiosity-driven (green)
        signal_is_fear = avg_surprise <= 0.4
        signal_gate = {
            "status": "yellow" if signal_is_fear else "green",
            "quality": "fear" if signal_is_fear else "curiosity",
            "avg_surprise_level": round(avg_surprise, 3),
            "note": (
                "Low surprise levels may indicate routine or fear-driven work. "
                "Run mos-signal-check before acting on institutional impulse."
                if signal_is_fear
                else "High surprise levels indicate curiosity-driven growth — good signal quality."
            ),
        }

        # GENERATION GATE: always pending human — can't automate 7th-gen judgment
        generation_gate = {
            "status": "pending_human",
            "question": (
                "Does scaling this serve the 7th generation, or just this quarter's metrics? "
                "Does it grow tall enough to give freely — or only wide enough to capture?"
            ),
        }

        # Overall readiness
        gates_open = sum([proof_gate_open, signal_is_fear])  # generation gate always pending
        if proof_gate_open:
            overall = "NOT_READY"
            primary_blocker = "proof_gate"
            guidance = (
                "Deepen roots: find 1 real external user and solve 1 real problem for them. "
                "Record it with proof_of_value(). Until then, give freely at the current scale."
            )
        elif signal_is_fear:
            overall = "PARTIAL"
            primary_blocker = "signal_gate"
            guidance = (
                "Proof gate is green — good. But signal quality is low. "
                "Run mos-signal-check before any institutional move. "
                "Curiosity-driven scale is generative; fear-driven scale is hollow."
            )
        else:
            overall = "PARTIAL"  # generation gate still pending human
            primary_blocker = "generation_gate"
            guidance = (
                "Proof and signal gates are green. Now answer the generation question: "
                "does this serve the 7th generation? Sit with it a day. "
                "If yes, the institutional impulse is ready to act. Give freely."
            )

        return ToolResult(ok=True, output={
            "proof_gate": proof_gate,
            "signal_gate": signal_gate,
            "generation_gate": generation_gate,
            "overall_readiness": overall,
            "primary_blocker": primary_blocker,
            "guidance": guidance,
            "observed_at": _utc_now(),
        })


# ── WedgeCalibratorTool ──────────────────────────────────────────────────────


class _WedgeArgs(BaseModel):
    days: int = Field(default=90, ge=7, le=365, description="How many days of experience atoms to analyze.")


class WedgeCalibratorTool(Tool[_WedgeArgs]):
    name = "wedge_calibrator"
    tier = 0
    description = (
        "Discover the problem domain where Aria shows the most consistent, "
        "surprising value. Clusters experience atoms by domain tag and scores each "
        "by (count × avg_surprise_level). Returns top wedge candidates — the answer "
        "to 'what should we give freely, and to whom?' Use before any platform move."
    )
    failure_modes = ("db_unavailable",)
    Args = _WedgeArgs

    async def execute(self, args: _WedgeArgs, *, trace_id: str) -> ToolResult:
        try:
            by_domain = await asyncio.to_thread(_get_experience_atoms_by_domain, args.days)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=True, output={
                "top_wedges": [],
                "best_wedge": None,
                "confidence": "low",
                "total_atoms": 0,
                "note": f"DB unavailable: {e}",
            })

        if not by_domain:
            return ToolResult(ok=True, output={
                "top_wedges": [],
                "best_wedge": None,
                "confidence": "low",
                "total_atoms": 0,
                "note": f"No experience atoms in the last {args.days} days. Collect more data first.",
            })

        total_atoms = sum(len(v) for v in by_domain.values())

        scored = []
        for domain, surprises in by_domain.items():
            avg = sum(surprises) / len(surprises)
            score = round(len(surprises) * avg, 3)
            scored.append({
                "domain": domain,
                "score": score,
                "atom_count": len(surprises),
                "avg_surprise": round(avg, 3),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_wedges = scored[:5]
        best_wedge = top_wedges[0]["domain"] if top_wedges else None

        if total_atoms < 10:
            confidence = "low"
        elif total_atoms < 50:
            confidence = "medium"
        else:
            confidence = "high"

        note = (
            f"With {total_atoms} atoms, this is {'early signal' if confidence == 'low' else 'solid signal'}. "
            f"Best wedge: '{best_wedge}' — this is where giving freely has the most impact."
            if best_wedge else "No wedge identified yet — collect more experience atoms."
        )

        return ToolResult(ok=True, output={
            "top_wedges": top_wedges,
            "best_wedge": best_wedge,
            "confidence": confidence,
            "total_atoms": total_atoms,
            "note": note,
        })


__all__ = ["InstitutionalImpulseCheckTool", "WedgeCalibratorTool"]
