"""tools/reflection_tools.py — Weekly synthesis tools (M59).

  weekly_reflection()       T0 — synthesize 7-day window into a reflection atom
  reflection_history()      T0 — read last N weekly-reflection atoms as trend list
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.memory import Atom, write_atom
except ImportError:
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _week_label() -> str:
    """Returns ISO week string like '2026-W25'."""
    dt = datetime.now(timezone.utc)
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


def _read_atoms_by_type(atom_type: str, limit: int = 50) -> list[dict]:
    if open_atoms_db is None:
        return []
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT atom_id, summary, content_ref, created_at, scope_tags "
            "FROM atoms WHERE type = ? AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (atom_type, limit),
        ).fetchall()
        results = []
        for row in rows:
            try:
                content = json.loads(row[2]) if isinstance(row[2], str) else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
            except Exception:  # noqa: BLE001
                data = {}
            results.append({
                "atom_id": row[0],
                "summary": row[1],
                "content": data,
                "created_at": row[3],
                "scope_tags": json.loads(row[4]) if isinstance(row[4], str) else (row[4] or []),
            })
        conn.close()
        return results
    except Exception:  # noqa: BLE001
        return []


def _get_weekly_metrics(days: int = 7) -> dict:
    try:
        from sovereign_agent.tools.eval_tools import _compute_metrics, _score_metrics
        metrics = _compute_metrics(days)
        score, band = _score_metrics(metrics)
        return {"score": score, "band": band, **metrics}
    except Exception:  # noqa: BLE001
        return {"score": 0, "band": "baseline"}


def _get_confirmed_hypothesis_count(days: int = 7) -> int:
    if open_atoms_db is None:
        return 0
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        conn = open_atoms_db()
        count = conn.execute(
            "SELECT COUNT(*) FROM atoms "
            "WHERE type='hypothesis-result' AND created_at >= ? "
            "AND content_ref LIKE '%\"confirmed\"%'",
            (since,),
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:  # noqa: BLE001
        return 0


# ── WeeklyReflectionTool ──────────────────────────────────────────────────────

class _ReflectionArgs(BaseModel):
    next_week_intention: str = Field(
        default="",
        description="Optional intention or focus for the coming week (used as a prompt for autonomous planning).",
    )


class WeeklyReflectionTool(Tool[_ReflectionArgs]):
    name = "weekly_reflection"
    tier = 0
    description = (
        "Synthesize the last 7 days into a weekly-reflection atom. "
        "Aggregates eval score, session briefs, surprising experiences, and confirmed hypothesis count. "
        "No LLM call — pure aggregation math. Call Monday morning (or on demand) to write the crew brief. "
        "Pairs with the weekly-reflection cron entry."
    )
    failure_modes = ("db_write_failed",)
    Args = _ReflectionArgs

    async def execute(self, args: _ReflectionArgs, *, trace_id: str) -> ToolResult:
        if open_atoms_db is None or Atom is None or write_atom is None:
            return ToolResult(ok=False, error="DB or write_atom unavailable.")

        try:
            # 1. Eval metrics
            metrics = await asyncio.to_thread(_get_weekly_metrics, 7)
            score = metrics.get("score", 0)

            # 2. Session briefs
            briefs = await asyncio.to_thread(_read_atoms_by_type, "session-brief", 3)
            brief_summaries = [b["summary"] for b in briefs]

            # 3. High-surprise experiences
            all_experiences = await asyncio.to_thread(_read_atoms_by_type, "experience", 50)
            surprising = [
                e for e in all_experiences
                if e["content"].get("surprise_level", 0.0) > 0.6
            ]
            top_experiences = [{"summary": e["summary"], "surprise": e["content"].get("surprise_level", 0.0)} for e in surprising[:5]]

            # 4. Memorable moment (highest-surprise)
            if surprising:
                best = max(surprising, key=lambda e: e["content"].get("surprise_level", 0.0))
                memorable_moment = best["summary"]
            else:
                memorable_moment = "quiet week — no high-surprise events logged"

            # 5. Confirmed hypotheses
            confirm_count = await asyncio.to_thread(_get_confirmed_hypothesis_count, 7)

            week_label = _week_label()
            reflection = {
                "period": week_label,
                "score": score,
                "score_band": metrics.get("band", "baseline"),
                "top_experiences": top_experiences,
                "memorable_moment": memorable_moment,
                "recent_briefs": brief_summaries,
                "confirmed_hypotheses_this_week": confirm_count,
                "hypothesis_confirm_rate": metrics.get("hypothesis_confirm_rate", 0.0),
                "open_questions_carried": "see hypothesis_queue()",
                "next_week_intention": args.next_week_intention or "continue current trajectory",
                "metrics": {k: v for k, v in metrics.items() if k not in ("score", "band")},
            }

            atom = Atom(
                type="weekly-reflection",
                summary=f"[{week_label}] score={score} — {memorable_moment[:80]}",
                content_ref={"kind": "inline", "content": json.dumps(reflection)},
                claims=[],
                parents=[trace_id],
                confidence=1.0,
                created_by={"actor": "reflection-crown", "version": "M59"},
                scope_tags=["weekly-reflection", week_label],
            )
            conn = open_atoms_db()
            atom_id = await asyncio.to_thread(write_atom, conn, atom)
            conn.commit()

            return ToolResult(ok=True, output={
                "atom_id": str(atom_id),
                "week": week_label,
                "score": score,
                "memorable_moment": memorable_moment,
                "confirmed_hypotheses_this_week": confirm_count,
                "next_week_intention": reflection["next_week_intention"],
                "reflection": reflection,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"weekly_reflection failed: {e}")


# ── ReflectionHistoryTool ─────────────────────────────────────────────────────

class _HistoryArgs(BaseModel):
    limit: int = Field(default=8, ge=1, le=52, description="Number of weekly reflections to return.")


class ReflectionHistoryTool(Tool[_HistoryArgs]):
    name = "reflection_history"
    tier = 0
    description = (
        "Read the last N weekly-reflection atoms as a trend list. "
        "Returns [{period, score, score_band, memorable_moment}] newest first. "
        "Use to see score trajectory and identify patterns across weeks."
    )
    failure_modes = ("db_unavailable",)
    Args = _HistoryArgs

    async def execute(self, args: _HistoryArgs, *, trace_id: str) -> ToolResult:
        try:
            atoms = await asyncio.to_thread(_read_atoms_by_type, "weekly-reflection", args.limit)
            trend = []
            for a in atoms:
                c = a["content"]
                trend.append({
                    "period": c.get("period", "?"),
                    "score": c.get("score", 0),
                    "score_band": c.get("score_band", "?"),
                    "memorable_moment": c.get("memorable_moment", ""),
                    "created_at": a["created_at"],
                })
            return ToolResult(ok=True, output={
                "trend": trend,
                "count": len(trend),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"reflection_history failed: {e}")


__all__ = ["WeeklyReflectionTool", "ReflectionHistoryTool"]
