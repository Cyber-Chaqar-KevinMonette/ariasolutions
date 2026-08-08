"""tools/proof_tools.py — Value proof infrastructure (M67).

  proof_of_value()   T1 — record a witnessed instance of external value delivery
  proof_history()    T0 — trend of proof instances; feeds institutional_impulse_check()
  giving_ledger()    T0 — measure of giving freely (canopy of the tree)
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

try:
    from sovereign_agent.memory import Atom, write_atom
except ImportError:
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── DB helpers ───────────────────────────────────────────────────────────────


def _read_proof_atoms() -> list[dict]:
    """Return all proof-of-value atoms as dicts."""
    if open_atoms_db is None:
        return []
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref, created_at FROM atoms "
            "WHERE type='proof-of-value' AND superseded_at IS NULL "
            "ORDER BY created_at DESC",
        ).fetchall()
        conn.close()
        result = []
        for (content_ref, created_at) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else (content_ref or {})
                content_str = cr.get("content", "{}")
                content = json.loads(content_str) if isinstance(content_str, str) else (content_str or {})
                content["_created_at"] = created_at
                result.append(content)
            except Exception:  # noqa: BLE001
                pass
        return result
    except Exception:  # noqa: BLE001
        return []


def _count_giving_atoms(days: int) -> tuple[int, str | None]:
    """Return (count, most_generous_day) from experience + proof atoms in last N days."""
    if open_atoms_db is None:
        return 0, None
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT created_at FROM atoms "
            "WHERE type IN ('experience', 'proof-of-value') "
            "AND superseded_at IS NULL AND created_at >= ?",
            (cutoff,),
        ).fetchall()
        conn.close()
        if not rows:
            return 0, None
        counts_by_day: dict[str, int] = {}
        for (created_at,) in rows:
            if created_at:
                day = str(created_at)[:10]
                counts_by_day[day] = counts_by_day.get(day, 0) + 1
        total = sum(counts_by_day.values())
        most_generous = max(counts_by_day, key=lambda d: counts_by_day[d]) if counts_by_day else None
        return total, most_generous
    except Exception:  # noqa: BLE001
        return 0, None


# ── ProofOfValueTool ─────────────────────────────────────────────────────────


class _ProofArgs(BaseModel):
    person_name: str = Field(description="Name of the person who received value.")
    problem_solved: str = Field(description="What problem did Aria help solve?")
    value_delivered: str = Field(description="What was the value delivered? Be specific.")
    was_unprompted: bool = Field(
        description="Was this value delivered without the person explicitly asking Aria to help?",
    )
    person_is_builder: bool = Field(
        default=False,
        description="Is this person one of Aria's builders (e.g., Kevin)? "
                    "Builder-internal proof doesn't count toward the external proof gate.",
    )


class ProofOfValueTool(Tool[_ProofArgs]):
    name = "proof_of_value"
    tier = 1  # T1: making a proof claim is intentional — requires operator action
    description = (
        "Record a witnessed instance of Aria delivering real value to a real person. "
        "This is the unit of proof that feeds institutional_impulse_check()'s proof gate. "
        "T1 because proof claims are not casual — they require intentional operator recording. "
        "Set person_is_builder=False for external (non-Kevin) recipients — those are the "
        "instances that count toward the proof gate."
    )
    failure_modes = ("db_write_failed",)
    Args = _ProofArgs

    async def execute(self, args: _ProofArgs, *, trace_id: str) -> ToolResult:
        if open_atoms_db is None or Atom is None or write_atom is None:
            return ToolResult(ok=False, error="DB or write_atom unavailable.")

        content = {
            "person_name": args.person_name,
            "problem_solved": args.problem_solved,
            "value_delivered": args.value_delivered,
            "was_unprompted": args.was_unprompted,
            "person_is_builder": args.person_is_builder,
            "recorded_at": _utc_now(),
        }
        scope_tags = ["proof", "value-delivery"]
        if args.person_is_builder:
            scope_tags.append("internal-proof")
        else:
            scope_tags.append("external-proof")

        summary = (
            f"[proof/{args.person_name}] {args.problem_solved[:80]}"
        )

        atom = Atom(
            type="proof-of-value",
            summary=summary,
            content_ref={"kind": "inline", "content": json.dumps(content)},
            claims=[],
            parents=[trace_id],
            confidence=1.0,
            created_by={"actor": "proof-crown", "version": "M67"},
            scope_tags=scope_tags,
        )
        try:
            conn = open_atoms_db()
            atom_id = await asyncio.to_thread(write_atom, conn, atom)
            conn.commit()
            return ToolResult(ok=True, output={
                "atom_id": str(atom_id),
                "person_name": args.person_name,
                "person_is_builder": args.person_is_builder,
                "proof_gate_eligible": not args.person_is_builder,
                "summary": summary,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"proof_of_value failed: {e}")


# ── ProofHistoryTool ─────────────────────────────────────────────────────────


class _HistoryArgs(BaseModel):
    pass


class ProofHistoryTool(Tool[_HistoryArgs]):
    name = "proof_history"
    tier = 0
    description = (
        "Read all proof-of-value atoms and return summary counts. "
        "proof_gate_met=True when external_count >= 1. "
        "This is the truth source for institutional_impulse_check()'s proof gate."
    )
    failure_modes = ("db_unavailable",)
    Args = _HistoryArgs

    async def execute(self, args: _HistoryArgs, *, trace_id: str) -> ToolResult:
        try:
            atoms = await asyncio.to_thread(_read_proof_atoms)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=True, output={
                "total_count": 0, "external_count": 0, "internal_count": 0,
                "most_recent": None, "proof_gate_met": False,
                "note": f"DB unavailable: {e}",
            })

        total = len(atoms)
        external = [a for a in atoms if not a.get("person_is_builder", True)]
        internal = [a for a in atoms if a.get("person_is_builder", True)]
        most_recent = atoms[0].get("person_name") if atoms else None

        return ToolResult(ok=True, output={
            "total_count": total,
            "external_count": len(external),
            "internal_count": len(internal),
            "most_recent_person": most_recent,
            "proof_gate_met": len(external) >= 1,
            "note": (
                f"Proof gate MET: {len(external)} external instance(s) on record."
                if len(external) >= 1
                else "Proof gate OPEN: no external proof yet. Find 1 real external user."
            ),
        })


# ── GivingLedgerTool ─────────────────────────────────────────────────────────


class _GivingArgs(BaseModel):
    days: int = Field(default=30, ge=1, le=365, description="Window in days.")


class GivingLedgerTool(Tool[_GivingArgs]):
    name = "giving_ledger"
    tier = 0
    description = (
        "Track 'giving freely' — the canopy of the institutional impulse tree. "
        "Counts experience + proof-of-value atoms as instances of giving. "
        "Returns: value_given_count, most_generous_day, giving_velocity. "
        "Pure aggregation — no LLM call."
    )
    failure_modes = ("db_unavailable",)
    Args = _GivingArgs

    async def execute(self, args: _GivingArgs, *, trace_id: str) -> ToolResult:
        try:
            count, most_generous_day = await asyncio.to_thread(_count_giving_atoms, args.days)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=True, output={
                "value_given_count": 0,
                "most_generous_day": None,
                "giving_velocity_per_week": 0.0,
                "note": f"DB unavailable: {e}",
            })

        velocity = round((count / args.days) * 7, 1) if args.days > 0 else 0.0

        return ToolResult(ok=True, output={
            "days": args.days,
            "value_given_count": count,
            "most_generous_day": most_generous_day,
            "giving_velocity_per_week": velocity,
            "note": (
                f"{count} giving instance(s) in last {args.days} days "
                f"({velocity}/week). "
                + (f"Most generous day: {most_generous_day}." if most_generous_day else "No activity yet.")
            ),
        })


__all__ = ["ProofOfValueTool", "ProofHistoryTool", "GivingLedgerTool"]
