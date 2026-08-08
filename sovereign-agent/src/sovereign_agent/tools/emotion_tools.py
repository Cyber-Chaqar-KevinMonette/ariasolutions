"""tools/emotion_tools.py — 8-dimensional emotion engine tools (M44).

  get_emotions()                                      T0 — derive current EmotionState
  emotion_note(dimension, context, intensity)         T1 — record emotional observation
  emotion_history(limit=10)                           T0 — past emotion atoms
  emotion_report()                                    T0 — session emotional arc summary
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level imports for testability
try:
    from sovereign_agent.emotion import derive_emotions, emotion_to_mood, EmotionState
except ImportError:
    derive_emotions = None  # type: ignore[assignment]
    emotion_to_mood = None  # type: ignore[assignment]
    EmotionState = None  # type: ignore[assignment]

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.memory import Atom, write_atom
except ImportError:
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]

_VALID_DIMENSIONS = frozenset({
    "focus", "curiosity", "concern", "satisfaction",
    "fatigue", "care", "enthusiasm", "uncertainty",
})


# ── get_emotions ──────────────────────────────────────────────────────────────


class _GetEmotionsArgs(BaseModel):
    pass


class GetEmotionsTool(Tool[_GetEmotionsArgs]):
    name = "get_emotions"
    tier = 0
    description = (
        "Derive Aria's current 8-dimensional emotional state from observable signals. "
        "Returns focus, curiosity, concern, satisfaction, fatigue, care, enthusiasm, uncertainty "
        "(all 0.0-1.0). All values are inferred from real signals — not declared. "
        "Call at session start, when concern may be elevated, or when Kevin asks. "
        "When concern > 0.7: report proactively before continuing work."
    )
    failure_modes = ("emotion_engine_unavailable",)
    Args = _GetEmotionsArgs

    async def execute(self, args: _GetEmotionsArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            state = await asyncio.to_thread(derive_emotions)
            return ToolResult(ok=True, output={
                "dimensions": state.scores(),
                "primary_emotion": state.primary_emotion,
                "narrative": state.narrative,
                "derived_at": state.derived_at,
                "mood": emotion_to_mood(state),
                "signals": state.signals,
                "attention": (
                    "CONCERN ELEVATED — report to Kevin before continuing."
                    if state.concern > 0.7 else None
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"get_emotions failed: {e}")


# ── emotion_note ──────────────────────────────────────────────────────────────


class _EmotionNoteArgs(BaseModel):
    dimension: str = Field(
        description=(
            "Which emotional dimension this note applies to: "
            "focus | curiosity | concern | satisfaction | fatigue | care | enthusiasm | uncertainty"
        ),
    )
    context: str = Field(
        max_length=500,
        description="What triggered this emotional note (what happened).",
    )
    intensity: float = Field(
        ge=0.0,
        le=1.0,
        description="Intensity of this emotion in this moment (0.0-1.0).",
    )


class EmotionNoteTool(Tool[_EmotionNoteArgs]):
    name = "emotion_note"
    tier = 1
    description = (
        "Record an in-the-moment emotional observation. "
        "Use when something unexpected or significant shifts your emotional state. "
        "Writes an atom for historical analysis. Aria is honest about her state — "
        "not performatively positive."
    )
    failure_modes = ("invalid_dimension", "atom_write_failed")
    Args = _EmotionNoteArgs

    async def execute(self, args: _EmotionNoteArgs, *, trace_id: str) -> ToolResult:
        if args.dimension not in _VALID_DIMENSIONS:
            return ToolResult(
                ok=False,
                error=f"Invalid dimension {args.dimension!r}. Valid: {sorted(_VALID_DIMENSIONS)}",
            )
        try:
            import json as _json

            atom = Atom(
                type="emotion-note",
                summary=f"{args.dimension} ({args.intensity:.0%}): {args.context[:100]}",
                content_ref={"kind": "inline", "content": _json.dumps({
                    "dimension": args.dimension,
                    "context": args.context,
                    "intensity": args.intensity,
                })},
                claims=[],
                parents=[trace_id],
                confidence=1.0,
                created_by={"actor": "emotion-crown", "version": "M44"},
                scope_tags=["emotion"],
            )
            conn = open_atoms_db()
            try:
                atom_id = await asyncio.to_thread(write_atom, conn, atom)
                await asyncio.to_thread(conn.commit)
            finally:
                conn.close()

            return ToolResult(ok=True, output={
                "atom_id": atom_id,
                "dimension": args.dimension,
                "intensity": args.intensity,
                "context": args.context,
                "message": f"Emotional note recorded: {args.dimension} at {args.intensity:.0%}.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"emotion_note failed: {e}")


# ── emotion_history ───────────────────────────────────────────────────────────


class _HistoryArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    dimension_filter: Optional[str] = Field(
        default=None,
        description="Filter by dimension name. Omit for all.",
    )


class EmotionHistoryTool(Tool[_HistoryArgs]):
    name = "emotion_history"
    tier = 0
    description = (
        "Read past emotional observations. Returns emotion-note atoms sorted newest-first. "
        "Use for self-reflection: what has been triggering concern? when was enthusiasm highest?"
    )
    failure_modes = ("atom_read_failed",)
    Args = _HistoryArgs

    async def execute(self, args: _HistoryArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            import json as _json

            conn = open_atoms_db()
            try:
                cur = conn.execute(
                    "SELECT atom_id, summary, content_json, created_at FROM atoms "
                    "WHERE type='emotion-note' AND superseded_at IS NULL "
                    "ORDER BY created_at DESC LIMIT ?",
                    (args.limit * 2,),
                )
                rows = cur.fetchall()
            finally:
                conn.close()

            entries = []
            for atom_id, summary, content_json, created_at in rows:
                try:
                    data = _json.loads(content_json or "{}")
                except Exception:
                    data = {}
                dim = data.get("dimension", "")
                if args.dimension_filter and dim != args.dimension_filter:
                    continue
                entries.append({
                    "atom_id": atom_id,
                    "dimension": dim,
                    "intensity": data.get("intensity", 0.0),
                    "context": data.get("context", summary),
                    "created_at": created_at,
                })
                if len(entries) >= args.limit:
                    break

            return ToolResult(ok=True, output={
                "entries": entries,
                "count": len(entries),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"emotion_history failed: {e}")


# ── emotion_report ────────────────────────────────────────────────────────────


class _ReportArgs(BaseModel):
    pass


class EmotionReportTool(Tool[_ReportArgs]):
    name = "emotion_report"
    tier = 0
    description = (
        "Generate a session emotional arc summary. Derives current state and reads "
        "recent emotion notes to describe the emotional trajectory of this session. "
        "Use at session end or when Kevin asks how you're doing."
    )
    failure_modes = ("emotion_engine_unavailable",)
    Args = _ReportArgs

    async def execute(self, args: _ReportArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            state = await asyncio.to_thread(derive_emotions)
            scores = state.scores()

            # Find peaks and lows
            peak_pos = max(
                (d for d in scores if d not in ("concern", "fatigue", "uncertainty")),
                key=scores.__getitem__,
            )
            peak_concern = max(
                ("concern", "fatigue", "uncertainty"),
                key=scores.__getitem__,
            )

            concerns_to_flag = []
            if state.concern > 0.5:
                concerns_to_flag.append(f"concern at {state.concern:.0%}")
            if state.fatigue > 0.5:
                concerns_to_flag.append(f"fatigue at {state.fatigue:.0%}")
            if state.uncertainty > 0.6:
                concerns_to_flag.append(f"uncertainty at {state.uncertainty:.0%}")

            return ToolResult(ok=True, output={
                "current_state": scores,
                "primary_emotion": state.primary_emotion,
                "narrative": state.narrative,
                "peak_positive": peak_pos,
                "peak_positive_value": round(scores[peak_pos], 3),
                "peak_concern_dimension": peak_concern,
                "peak_concern_value": round(scores[peak_concern], 3),
                "concerns_to_flag": concerns_to_flag,
                "overall_assessment": (
                    "session well"
                    if state.concern < 0.4 and state.satisfaction > 0.5
                    else "attention needed" if state.concern > 0.6
                    else "session nominal"
                ),
                "signals_summary": {
                    "tool_events": state.signals.get("tool_event_count", 0),
                    "errors": state.signals.get("error_count", 0),
                    "commits": state.signals.get("commit_count", 0),
                    "lessons": state.signals.get("lesson_count", 0),
                },
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"emotion_report failed: {e}")


__all__ = [
    "GetEmotionsTool",
    "EmotionNoteTool",
    "EmotionHistoryTool",
    "EmotionReportTool",
]
