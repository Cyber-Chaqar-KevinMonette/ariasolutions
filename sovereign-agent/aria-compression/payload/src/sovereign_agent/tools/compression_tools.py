"""
tools/compression_tools.py — Context compression tools (M36).

  context_stats()       T0 — event count, estimated tokens, compression
                             opportunity score, oldest event age
  compress_context()    T1 — compress old events into a summary atom;
                             no events deleted; returns what was preserved
  read_compressed_context()  T0 — retrieve latest compression summary
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _StatsArgs(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to analyze. Omit for current session.",
    )


class ContextStatsTool(Tool[_StatsArgs]):
    name = "context_stats"
    tier = 0
    description = (
        "Show compression statistics for the current session: event count, "
        "estimated token usage, compression opportunity score (0–1), and "
        "how old the oldest events are. When compression_opportunity > 0.6 "
        "and you have used many tokens, call compress_context() to reclaim "
        "context budget."
    )
    failure_modes = ("events_db_unavailable",)
    Args = _StatsArgs

    async def execute(self, args: _StatsArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.compression import compression_opportunity_score
            events = await asyncio.to_thread(_load_recent_events, SETTINGS.paths)
            score = compression_opportunity_score(events)
            oldest_age = _oldest_age(events)
            return ToolResult(ok=True, output={
                "event_count": len(events),
                "estimated_tokens": len(events) * 120,
                "compression_opportunity": score,
                "oldest_event_age_seconds": oldest_age,
                "high_value_event_count": sum(
                    1 for e in events
                    if e.get("flag", "") in {
                        "commit-d", "decision-d", "workflow-create-d",
                        "blocked-x", "lesson-d", "context-compressed-d",
                    }
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"stats failed: {e}")


class _CompressArgs(BaseModel):
    preserve_goals: bool = Field(default=True, description="Preserve goal/plan events.")
    preserve_decisions: bool = Field(default=True, description="Preserve decision events.")
    min_age_seconds: int = Field(
        default=300, ge=0,
        description="Only compress events older than this many seconds.",
    )


class CompressContextTool(Tool[_CompressArgs]):
    name = "compress_context"
    tier = 1
    description = (
        "Compress old session events into a value-preserving summary atom. "
        "High-value events (commits, decisions, lessons, blocked steps) are "
        "always preserved verbatim. Low-value events (token counts, cache hits, "
        "boot noise) are compressed to counts. The summary is written as a "
        "context-compressed-d atom and surfaces via read_session() on next boot. "
        "IMPORTANT: No events are deleted — this is additive, not destructive."
    )
    failure_modes = ("events_db_unavailable", "atom_write_failed")
    Args = _CompressArgs

    async def execute(self, args: _CompressArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.compression import compress_events
            from sovereign_agent.db import open_atoms_db
            from sovereign_agent.memory import Atom, write_atom

            events = await asyncio.to_thread(_load_recent_events, SETTINGS.paths)
            if not events:
                return ToolResult(ok=True, output={
                    "compressed": False,
                    "reason": "no events to compress",
                })

            extra_preserve: set[str] = set()
            if args.preserve_goals:
                extra_preserve |= {"workflow-create-d", "plan-approval-d"}
            if args.preserve_decisions:
                extra_preserve |= {"decision-d"}

            ctx = compress_events(
                events,
                preserve_tags=extra_preserve,
                min_age_seconds=args.min_age_seconds,
            )

            # Write summary as atom
            atom = Atom(
                type="context-compressed",
                summary=(
                    f"Session compression: {ctx.preserved_count} high-value, "
                    f"{ctx.compressed_count} compressed, "
                    f"~{ctx.tokens_saved_estimate} tokens saved"
                ),
                content_ref={"kind": "inline", "content": ctx.summary},
                claims=[],
                parents=[trace_id],
                confidence=1.0,
                created_by={"actor": "compression", "version": "M36"},
                scope_tags=["context-compressed"],
            )

            def _write():
                conn = open_atoms_db()
                try:
                    aid = write_atom(conn, atom)
                    conn.commit()
                    return aid
                finally:
                    conn.close()

            atom_id = await asyncio.to_thread(_write)
            return ToolResult(ok=True, output={
                "compressed": True,
                "atom_id": atom_id,
                "preserved_count": ctx.preserved_count,
                "compressed_count": ctx.compressed_count,
                "tokens_saved_estimate": ctx.tokens_saved_estimate,
                "summary_preview": ctx.summary[:300],
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"compression failed: {e}")


class _ReadArgs(BaseModel):
    limit: int = Field(default=1, ge=1, le=10, description="Number of compression summaries to return.")


class ReadCompressedContextTool(Tool[_ReadArgs]):
    name = "read_compressed_context"
    tier = 0
    description = (
        "Retrieve the most recent context compression summary. Shows what was "
        "preserved and what was compressed in the last compress_context() call. "
        "Use at session start to restore compressed context efficiently."
    )
    failure_modes = ("atom_db_unavailable", "no_compression_found")
    Args = _ReadArgs

    async def execute(self, args: _ReadArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.db import open_atoms_db
            results = await asyncio.to_thread(
                _query_compression_atoms, args.limit
            )
            if not results:
                return ToolResult(
                    ok=False,
                    error="no compression summaries found — run compress_context() first",
                )
            return ToolResult(ok=True, output={"summaries": results, "count": len(results)})
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read failed: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_recent_events(paths) -> list[dict]:
    """Load events from the events NDJSON directory."""
    import json
    events = []
    events_dir = paths.events_dir if hasattr(paths, "events_dir") else paths.data_dir / "events"
    if not events_dir.exists():
        return events
    for f in sorted(events_dir.glob("*.ndjson"))[-3:]:  # last 3 files
        try:
            for line in f.read_text().splitlines():
                if line.strip():
                    events.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return events


def _oldest_age(events: list[dict]) -> float:
    """Return age in seconds of the oldest event, or 0."""
    now = time.time()
    oldest = min(
        (float(e.get("created_at") or e.get("ts") or now) for e in events),
        default=now,
    )
    return round(now - oldest, 1)


def _query_compression_atoms(limit: int) -> list[dict]:
    """Query atoms db for context-compressed entries."""
    import json
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT atom_id, summary, content_ref, created_at "
            "FROM atoms WHERE type='context-compressed' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            content = {}
            try:
                content = json.loads(row[2]) if row[2] else {}
            except Exception:  # noqa: BLE001
                pass
            results.append({
                "atom_id": row[0],
                "summary": row[1],
                "content": content.get("content", ""),
                "created_at": row[3],
            })
        return results
    finally:
        conn.close()


__all__ = ["ContextStatsTool", "CompressContextTool", "ReadCompressedContextTool"]
