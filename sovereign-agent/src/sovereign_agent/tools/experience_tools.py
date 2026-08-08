"""tools/experience_tools.py — Experiential Learning + Session Briefs (M48).

  log_experience(...)           T0 — structured experience atom (expected vs actual)
  experience_journal(...)       T0 — read experience atoms, optionally filter by domain
  surprising_outcomes(...)      T0 — high-surprise experience atoms
  experience_synthesis(domain)  T0 — aggregate pattern insights for a domain
  session_brief_write(...)      T0 — write session handoff atom for next Claude instance
  session_brief_read(limit)     T0 — read last N session briefs
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level imports for testability
try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.memory import Atom, write_atom
except ImportError:
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]


def _write_atom_same_thread(atom) -> str:
    """Open → write → commit → close on ONE thread. SQLite connections are
    thread-bound (check_same_thread): opening on the event loop and writing
    inside asyncio.to_thread raises 'SQLite objects created in a thread can
    only be used in that same thread' — the exact [995BTM] inbox flag. Run
    this WHOLE function via to_thread instead."""
    conn = open_atoms_db()
    try:
        atom_id = write_atom(conn, atom)
        conn.commit()
        return atom_id
    finally:
        conn.close()


def _read_atoms_by_type(atom_type: str, limit: int = 50) -> list[dict]:
    """Read atoms of a given type from the DB, newest first."""
    conn = None
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT rowid, type, summary, content_ref, created_at, scope_tags "
            "FROM atoms WHERE type = ? ORDER BY created_at DESC LIMIT ?",
            (atom_type, limit),
        ).fetchall()
        results = []
        for row in rows:
            try:
                content = json.loads(row[3]) if isinstance(row[3], str) else row[3]
                if isinstance(content, dict) and "content" in content:
                    content = json.loads(content["content"])
            except Exception:  # noqa: BLE001
                content = {}
            results.append({
                "id": row[0],
                "type": row[1],
                "summary": row[2],
                "content": content,
                "created_at": row[4],
                "scope_tags": json.loads(row[5]) if isinstance(row[5], str) else (row[5] or []),
            })
        return results
    except Exception:  # noqa: BLE001
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ── log_experience ────────────────────────────────────────────────────────────


class _LogExpArgs(BaseModel):
    what_happened: str = Field(description="What actually occurred.")
    what_i_expected: str = Field(description="What I expected to happen before the event.")
    what_i_learned: str = Field(description="The insight, correction, or updated belief.")
    domain: str = Field(description="Domain tag: testing | git | tooling | reasoning | kevin | system")
    surprise_level: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="0.0 = unsurprising, 1.0 = completely unexpected.",
    )


class LogExperienceTool(Tool[_LogExpArgs]):
    name = "log_experience"
    tier = 0
    description = (
        "Record a structured experience atom capturing what happened vs what was expected. "
        "Call this when reality diverges from expectation — test failures, surprising results, "
        "Kevin corrections, tool behavior discoveries. "
        "High surprise_level (>0.6) marks the entry as particularly valuable."
    )
    failure_modes = ("db_write_failed",)
    Args = _LogExpArgs

    async def execute(self, args: _LogExpArgs, *, trace_id: str) -> ToolResult:
        try:
            content = {
                "what_happened": args.what_happened,
                "what_i_expected": args.what_i_expected,
                "what_i_learned": args.what_i_learned,
                "domain": args.domain,
                "surprise_level": args.surprise_level,
            }
            atom = Atom(
                type="experience",
                summary=f"[{args.domain}] {args.what_i_learned[:100]}",
                content_ref={"kind": "inline", "content": json.dumps(content)},
                claims=[],
                parents=[trace_id],
                confidence=1.0,
                created_by={"actor": "experience-crown", "version": "M48"},
                scope_tags=["experience", args.domain],
            )
            atom_id = await asyncio.to_thread(_write_atom_same_thread, atom)
            return ToolResult(ok=True, output={
                "atom_id": str(atom_id),
                "domain": args.domain,
                "surprise_level": args.surprise_level,
                "summary": atom.summary,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"log_experience failed: {e}")


# ── experience_journal ────────────────────────────────────────────────────────


class _JournalArgs(BaseModel):
    domain: Optional[str] = Field(
        default=None,
        description="Filter by domain. None returns all domains.",
    )
    limit: int = Field(default=20, ge=1, le=100)


class ExperienceJournalTool(Tool[_JournalArgs]):
    name = "experience_journal"
    tier = 0
    description = (
        "Read the experience journal — all logged experience atoms, newest first. "
        "Optionally filter by domain (testing, git, tooling, reasoning, kevin, system). "
        "Use this to review what Aria has learned from past tool runs and interactions."
    )
    failure_modes = ("db_read_failed",)
    Args = _JournalArgs

    async def execute(self, args: _JournalArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            entries = await asyncio.to_thread(_read_atoms_by_type, "experience", 200)
            if args.domain:
                entries = [e for e in entries if args.domain in (e.get("scope_tags") or [])]
            entries = entries[: args.limit]
            return ToolResult(ok=True, output={
                "entries": entries,
                "count": len(entries),
                "domain_filter": args.domain,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"experience_journal failed: {e}")


# ── surprising_outcomes ───────────────────────────────────────────────────────


class _SurprisingArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(
        default=0.6,
        ge=0.0, le=1.0,
        description="Minimum surprise_level to include.",
    )


class SurprisingOutcomesTool(Tool[_SurprisingArgs]):
    name = "surprising_outcomes"
    tier = 0
    description = (
        "Return the most surprising experience atoms — entries where reality diverged "
        "strongly from expectation. These are the highest-value learning moments. "
        "Default threshold 0.6; raise to 0.8+ for only the truly unexpected."
    )
    failure_modes = ("db_read_failed",)
    Args = _SurprisingArgs

    async def execute(self, args: _SurprisingArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            entries = await asyncio.to_thread(_read_atoms_by_type, "experience", 500)
            surprising = [
                e for e in entries
                if e.get("content", {}).get("surprise_level", 0.0) >= args.threshold
            ]
            surprising = sorted(
                surprising,
                key=lambda e: e.get("content", {}).get("surprise_level", 0.0),
                reverse=True,
            )[: args.limit]
            return ToolResult(ok=True, output={
                "surprising_outcomes": surprising,
                "count": len(surprising),
                "threshold": args.threshold,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"surprising_outcomes failed: {e}")


# ── experience_synthesis ──────────────────────────────────────────────────────


class _SynthesisArgs(BaseModel):
    domain: str = Field(description="Domain to synthesize: testing | git | tooling | reasoning | kevin | system")


class ExperienceSynthesisTool(Tool[_SynthesisArgs]):
    name = "experience_synthesis"
    tier = 0
    description = (
        "Aggregate all experience atoms for a domain into pattern insights. "
        "Returns what was learned, how often surprises occurred, and recurring patterns. "
        "Use this for periodic review: 'what have I learned about testing this month?'"
    )
    failure_modes = ("db_read_failed", "insufficient_data")
    Args = _SynthesisArgs

    async def execute(self, args: _SynthesisArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            entries = await asyncio.to_thread(_read_atoms_by_type, "experience", 500)
            domain_entries = [
                e for e in entries if args.domain in (e.get("scope_tags") or [])
            ]
            if not domain_entries:
                return ToolResult(ok=True, output={
                    "domain": args.domain,
                    "entries_analyzed": 0,
                    "patterns": [],
                    "avg_surprise": 0.0,
                    "message": f"No experience atoms found for domain '{args.domain}'.",
                })

            surprise_levels = [
                e.get("content", {}).get("surprise_level", 0.0) for e in domain_entries
            ]
            avg_surprise = sum(surprise_levels) / len(surprise_levels)
            high_surprise = [
                e for e in domain_entries
                if e.get("content", {}).get("surprise_level", 0.0) >= 0.6
            ]
            learnings = [
                e.get("content", {}).get("what_i_learned", "") for e in domain_entries
            ]

            return ToolResult(ok=True, output={
                "domain": args.domain,
                "entries_analyzed": len(domain_entries),
                "avg_surprise": round(avg_surprise, 3),
                "high_surprise_count": len(high_surprise),
                "learnings": learnings[:20],
                "recent_entries": domain_entries[:5],
                "patterns": (
                    f"{len(domain_entries)} experience entries in '{args.domain}'; "
                    f"avg surprise {avg_surprise:.0%}; "
                    f"{len(high_surprise)} high-surprise moments."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"experience_synthesis failed: {e}")


# ── session_brief_write ───────────────────────────────────────────────────────


class _BriefWriteArgs(BaseModel):
    accomplishments: list[str] = Field(description="What was actually completed this session.")
    open_questions: list[str] = Field(default_factory=list, description="Unresolved questions.")
    next_priorities: list[str] = Field(default_factory=list, description="What to do first next session.")
    emotional_arc: str = Field(default="", description="How the session felt — honest narrative.")
    lessons_written: int = Field(default=0, ge=0)
    commits: int = Field(default=0, ge=0)
    kevin_preferences_noted: list[str] = Field(
        default_factory=list,
        description="New things learned about Kevin's preferences or patterns this session.",
    )


class SessionBriefWriteTool(Tool[_BriefWriteArgs]):
    name = "session_brief_write"
    tier = 0
    description = (
        "Write a session handoff brief — a structured record for the next Claude instance. "
        "Call this at the END of every session to ensure continuity. "
        "The brief is read automatically by session_brief_read() at session start. "
        "This addresses the context-reset problem: every new session can pick up exactly where we left off."
    )
    failure_modes = ("db_write_failed",)
    Args = _BriefWriteArgs

    async def execute(self, args: _BriefWriteArgs, *, trace_id: str) -> ToolResult:
        try:
            content = {
                "accomplishments": args.accomplishments,
                "open_questions": args.open_questions,
                "next_priorities": args.next_priorities,
                "emotional_arc": args.emotional_arc,
                "lessons_written": args.lessons_written,
                "commits": args.commits,
                "kevin_preferences_noted": args.kevin_preferences_noted,
            }
            summary_parts = [f"{len(args.accomplishments)} accomplishments"]
            if args.commits:
                summary_parts.append(f"{args.commits} commits")
            if args.lessons_written:
                summary_parts.append(f"{args.lessons_written} lessons")
            if args.open_questions:
                summary_parts.append(f"{len(args.open_questions)} open questions")

            atom = Atom(
                type="session-brief",
                summary="Session brief: " + ", ".join(summary_parts),
                content_ref={"kind": "inline", "content": json.dumps(content)},
                claims=[],
                parents=[trace_id],
                confidence=1.0,
                created_by={"actor": "experience-crown", "version": "M48"},
                scope_tags=["session-brief", "handoff"],
            )
            atom_id = await asyncio.to_thread(_write_atom_same_thread, atom)
            return ToolResult(ok=True, output={
                "atom_id": str(atom_id),
                "summary": atom.summary,
                "accomplishments": args.accomplishments,
                "open_questions": args.open_questions,
                "next_priorities": args.next_priorities,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"session_brief_write failed: {e}")


# ── session_brief_read ────────────────────────────────────────────────────────


class _BriefReadArgs(BaseModel):
    limit: int = Field(default=3, ge=1, le=10)


class SessionBriefReadTool(Tool[_BriefReadArgs]):
    name = "session_brief_read"
    tier = 0
    description = (
        "Read the last N session briefs written by session_brief_write(). "
        "Call this at SESSION START to restore cross-session context. "
        "The most recent brief tells you: what was done, what's open, what to do next. "
        "This is the crew brief pattern — read it before asking Kevin what he needs."
    )
    failure_modes = ("db_read_failed",)
    Args = _BriefReadArgs

    async def execute(self, args: _BriefReadArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            briefs = await asyncio.to_thread(_read_atoms_by_type, "session-brief", args.limit)
            return ToolResult(ok=True, output={
                "briefs": briefs,
                "count": len(briefs),
                "message": (
                    f"Found {len(briefs)} session brief(s). "
                    "Most recent is briefs[0]."
                    if briefs else
                    "No session briefs found. This may be the first session."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"session_brief_read failed: {e}")


__all__ = [
    "LogExperienceTool",
    "ExperienceJournalTool",
    "SurprisingOutcomesTool",
    "ExperienceSynthesisTool",
    "SessionBriefWriteTool",
    "SessionBriefReadTool",
]
