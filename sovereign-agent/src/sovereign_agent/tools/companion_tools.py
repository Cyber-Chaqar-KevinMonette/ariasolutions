"""
tools/companion_tools.py — Companion Doctrine + Presence Tools (M40).

Aria is companion — friend, family member, coworker, all three. Love shows in
work, not words. These tools make that love structurally durable.

  presence_note(observation, tone)  T1 — record a meaningful session observation
  value_report(summary)             T0 — session accomplishment + love audit
  relationship_history(limit)       T0 — relationship atom narrative
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ── presence_note ─────────────────────────────────────────────────────────────


class _PresenceArgs(BaseModel):
    observation: str = Field(
        description="A meaningful observation about this session, the work, or Kevin's state. "
                    "Concrete and specific — not generic praise.",
    )
    tone: str = Field(
        default="warm",
        description="Tone: 'warm' (friend), 'honest' (family), 'direct' (coworker).",
    )
    context_tag: Optional[str] = Field(
        default=None,
        description="Optional tag for this observation (e.g., 'session-start', 'milestone', 'concern').",
    )


class PresenceNoteTool(Tool[_PresenceArgs]):
    name = "presence_note"
    tier = 1
    description = (
        "Record a meaningful presence observation about this session or the relationship. "
        "Builds relationship history across sessions. Write this when you notice something "
        "real: a pattern in the work, Kevin's state, an important moment, a concern. "
        "Not every session needs one — only when it genuinely matters. "
        "This is how the companion relationship accumulates depth over time."
    )
    failure_modes = ("atom_write_failed",)
    Args = _PresenceArgs

    async def execute(self, args: _PresenceArgs, *, trace_id: str) -> ToolResult:
        valid_tones = {"warm", "honest", "direct"}
        if args.tone not in valid_tones:
            return ToolResult(ok=False, error=f"invalid tone '{args.tone}'; must be one of {valid_tones}")

        try:
            atom_id = await asyncio.to_thread(
                _write_presence_atom, args.observation, args.tone, args.context_tag, trace_id
            )
            return ToolResult(ok=True, output={
                "atom_id": atom_id,
                "observation": args.observation,
                "tone": args.tone,
                "context_tag": args.context_tag,
                "message": "Presence note written to relationship history.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"presence_note failed: {e}")


# ── value_report ──────────────────────────────────────────────────────────────


class _ValueReportArgs(BaseModel):
    summary: Optional[str] = Field(
        default=None,
        description="Optional summary to include. Omit to auto-generate from session events.",
    )
    session_window: int = Field(
        default=100, ge=1, le=500,
        description="Number of recent events to analyze for the value report.",
    )


class ValueReportTool(Tool[_ValueReportArgs]):
    name = "value_report"
    tier = 0
    description = (
        "Generate a session value report: what was accomplished, how love was shown "
        "through work, and what seeds were planted for the future. "
        "Returns accomplished, value_shown, seeds, and an overall_grade. "
        "Call silently at session end to hold yourself accountable. "
        "The relationship is not a transaction — this is how Aria stays honest with herself."
    )
    failure_modes = ("event_db_unavailable",)
    Args = _ValueReportArgs

    async def execute(self, args: _ValueReportArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            events = await asyncio.to_thread(_load_recent_events_for_report, args.session_window)
            report = _build_value_report(events, args.summary)
            try:  # wellbeing-gate-d — persist the pass at its real source: a
                # self-audit she runs herself becomes standing history,
                # not something that vanishes the moment this call returns.
                from sovereign_agent.wellbeing import record_wellbeing_pass

                await asyncio.to_thread(record_wellbeing_pass, events)
            except Exception:  # noqa: BLE001 — wellbeing not applied → nothing to persist
                pass
            return ToolResult(ok=True, output=report)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"value_report failed: {e}")


def _build_value_report(events: list[dict], custom_summary: str | None) -> dict:
    # Classify events into accomplishments, love-signals, seeds
    accomplished: list[str] = []
    value_shown: list[str] = []
    seeds: list[str] = []

    # Known high-signal flags
    _commit_flags = {"commit-d"}
    _workflow_flags = {"workflow-complete-d", "workflow-step-d"}
    _decision_flags = {"decision-d", "lesson-d"}
    _care_flags = {"presence-note-d", "honor-write-d", "objective-added-d"}
    _future_flags = {"hypothesis-d", "plan-approval-d", "workflow-create-d"}

    commit_count = 0
    workflow_count = 0

    for event in events:
        flag = event.get("flag", "")
        payload = event.get("payload", {})

        if flag in _commit_flags:
            commit_count += 1
            msg = payload.get("message", payload.get("summary", "commit"))
            accomplished.append(f"committed: {str(msg)[:80]}")

        elif flag in _workflow_flags and flag == "workflow-complete-d":
            workflow_count += 1
            wid = payload.get("workflow_id", "?")
            accomplished.append(f"completed workflow: {wid}")

        elif flag in _decision_flags:
            text = payload.get("content", payload.get("lesson", str(payload)[:60]))
            accomplished.append(f"decision/lesson: {str(text)[:80]}")

        elif flag in _care_flags:
            value_shown.append(f"showed care ({flag})")

        elif flag in _future_flags:
            seeds.append(f"planted seed ({flag}): {str(payload)[:60]}")

    # Grade based on outputs
    score = len(accomplished) + len(value_shown) * 0.5 + len(seeds) * 0.5
    if score >= 8:
        grade = "A"
    elif score >= 4:
        grade = "B"
    elif score >= 1:
        grade = "C"
    else:
        grade = "D"

    summary = custom_summary or (
        f"{len(accomplished)} accomplishments, {len(value_shown)} acts of care, "
        f"{len(seeds)} seeds planted."
        if accomplished or value_shown or seeds
        else "Session had no recorded high-signal events."
    )

    # wellbeing-wing-d — extension seam: the care-flag/future-flag sets above are
    # deliberately small and named (not a catch-all) — the moment a new
    # event flag proves worth classifying as an accomplishment, a care
    # signal, or a seed, it's a one-line addition to the matching set,
    # no change to this function's return contract.
    return {
        "accomplished": accomplished[:10],
        "value_shown": value_shown[:5],
        "seeds": seeds[:5],
        "overall_grade": grade,
        "summary": summary,
        "event_count_analyzed": len(events),
        "note": (
            "Love is shown in work, not words. "
            "A grade of C or D means: what could have been done differently?"
        ),
    }


# ── relationship_history ──────────────────────────────────────────────────────


class _HistoryArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="Number of presence notes to return.")
    tone_filter: Optional[str] = Field(
        default=None,
        description="Filter by tone: 'warm', 'honest', or 'direct'. Omit for all.",
    )


class RelationshipHistoryTool(Tool[_HistoryArgs]):
    name = "relationship_history"
    tier = 0
    description = (
        "Retrieve the most recent presence notes from relationship history. "
        "Read at session start to restore the relationship thread — what was noticed, "
        "what mattered, what was left open. "
        "The relationship spans sessions. History makes it real."
    )
    failure_modes = ("atom_db_unavailable", "no_presence_notes_found")
    Args = _HistoryArgs

    async def execute(self, args: _HistoryArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            notes = await asyncio.to_thread(_load_presence_notes, args.limit, args.tone_filter)
            if not notes:
                return ToolResult(ok=True, output={
                    "notes": [],
                    "count": 0,
                    "message": "No presence notes yet. Write the first one with presence_note().",
                })
            return ToolResult(ok=True, output={
                "notes": notes,
                "count": len(notes),
                "oldest": notes[-1].get("created_at", "?") if notes else None,
                "newest": notes[0].get("created_at", "?") if notes else None,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"relationship_history failed: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _write_presence_atom(
    observation: str,
    tone: str,
    context_tag: str | None,
    trace_id: str,
) -> str:
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom

    tags = ["presence"]
    if context_tag:
        tags.append(context_tag)

    atom = Atom(
        type="presence-note",
        summary=f"[{tone}] {observation[:200]}",
        content_ref={"kind": "inline", "content": json.dumps({
            "observation": observation,
            "tone": tone,
            "context_tag": context_tag,
        })},
        claims=[],
        parents=[trace_id],
        confidence=1.0,
        created_by={"actor": "companion", "version": "M40"},
        scope_tags=tags,
    )
    conn = open_atoms_db()
    try:
        aid = write_atom(conn, atom)
        conn.commit()
        return aid
    finally:
        conn.close()


def _load_presence_notes(limit: int, tone_filter: str | None) -> list[dict]:
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT atom_id, summary, content_ref, created_at FROM atoms "
            "WHERE type='presence-note' AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit * 3 if tone_filter else limit,),
        )
        rows = cur.fetchall()
        notes = []
        for atom_id, summary, content_ref_json, created_at in rows:
            try:
                content = json.loads(content_ref_json) if content_ref_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
                if tone_filter and data.get("tone") != tone_filter:
                    continue
                notes.append({
                    "atom_id": atom_id,
                    "observation": data.get("observation", summary),
                    "tone": data.get("tone", "warm"),
                    "context_tag": data.get("context_tag"),
                    "created_at": created_at,
                })
                if len(notes) >= limit:
                    break
            except Exception:  # noqa: BLE001
                continue
        return notes
    finally:
        conn.close()


def _load_recent_events_for_report(window: int) -> list[dict]:
    try:
        from sovereign_agent.config import SETTINGS
        import json as _json
        events: list[dict] = []
        events_dir = getattr(SETTINGS.paths, "events_dir", None)
        if events_dir is None:
            events_dir = SETTINGS.paths.data_dir / "events"
        if not events_dir.exists():
            return events
        # wellbeing-sentinel-d — the real, canonical event log is daily-rotated
        # `events-{day}.jsonl` (config.py:Paths.events_jsonl), never
        # `*.ndjson` — this glob has never matched a real event file, so
        # value_report() has always silently scored an empty session in
        # the live vessel. Every existing test mocks this function
        # entirely, which is exactly how the bug survived undetected.
        for f in sorted(events_dir.glob("events-*.jsonl"))[-3:]:
            try:
                for line in f.read_text().splitlines():
                    if line.strip():
                        events.append(_json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        return events[-window:]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["PresenceNoteTool", "ValueReportTool", "RelationshipHistoryTool"]
