"""tools/atoms_compact_tool.py — Atom store compaction tools (M54 atoms-compact).

  atoms_compact_preview(before_days, atom_type)  T0 — preview only, no changes
  atoms_compact(before_days, atom_type, dry_run)  T2 — write summary atoms + supersede originals
  atoms_compact_status()                          T0 — sentinel health + store stats
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .. import __version__
from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.memory import write_atom
except ImportError:
    write_atom = None  # type: ignore[assignment]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _cutoff_iso(before_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=before_days)).isoformat()


def _gather_candidates(before_days: int, atom_type: str | None) -> list[dict]:
    """Return active atoms older than before_days, optionally filtered by type."""
    if open_atoms_db is None:
        return []
    cutoff = _cutoff_iso(before_days)
    conn = open_atoms_db()
    try:
        if atom_type:
            rows = conn.execute(
                "SELECT atom_id, type, summary, created_at FROM atoms "
                "WHERE superseded_at IS NULL AND created_at < ? AND type = ? "
                "ORDER BY type, created_at",
                (cutoff, atom_type),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT atom_id, type, summary, created_at FROM atoms "
                "WHERE superseded_at IS NULL AND created_at < ? "
                "ORDER BY type, created_at",
                (cutoff,),
            ).fetchall()
    finally:
        conn.close()
    return [{"atom_id": r[0], "type": r[1], "summary": r[2], "created_at": r[3]} for r in rows]


def _group_by_type_month(candidates: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group candidates by (type, YYYY-MM) for compaction."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for atom in candidates:
        month = (atom["created_at"] or "")[:7]  # YYYY-MM
        key = (atom["type"], month)
        groups.setdefault(key, []).append(atom)
    return groups


# ─── Preview Tool (T0) ────────────────────────────────────────────────────────

class _PreviewArgs(BaseModel):
    before_days: int = Field(
        default=90,
        description="Consider atoms older than this many days as candidates.",
        ge=7, le=3650,
    )
    atom_type: Optional[str] = Field(
        default=None,
        description="Restrict to one atom type (e.g. 'lesson', 'experience'). Omit for all.",
    )


class AtomsCompactPreviewTool(Tool[_PreviewArgs]):
    """Preview compaction candidates without making any changes."""

    name = "atoms_compact_preview"
    tier = 0
    description = (
        "Preview atoms compaction: shows how many atoms would be summarized and superseded "
        "if atoms_compact() were run with the same parameters. No changes are made."
    )
    failure_modes = ("db_unavailable",)
    Args = _PreviewArgs

    async def execute(self, args: _PreviewArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        await asyncio.sleep(0)
        candidates = await asyncio.to_thread(_gather_candidates, args.before_days, args.atom_type)
        if not candidates:
            return ToolResult(ok=True, output={
                "candidates": 0,
                "groups": 0,
                "message": (
                    f"No atoms older than {args.before_days} days"
                    + (f" of type '{args.atom_type}'" if args.atom_type else "")
                    + ". Nothing to compact."
                ),
            })

        groups = _group_by_type_month(candidates)
        group_summary = [
            {
                "type": atype,
                "month": month,
                "count": len(atoms),
                "summary_atoms_needed": 1,
            }
            for (atype, month), atoms in sorted(groups.items())
        ]
        return ToolResult(ok=True, output={
            "candidates": len(candidates),
            "groups": len(groups),
            "summary_atoms_would_create": len(groups),
            "message": (
                f"{len(candidates)} atoms → {len(groups)} summary atoms. "
                f"Run atoms_compact(before_days={args.before_days}, dry_run=False) to apply."
            ),
            "breakdown": group_summary,
        })


# ─── Compact Tool (T2) ────────────────────────────────────────────────────────

class _CompactArgs(BaseModel):
    before_days: int = Field(
        default=90,
        description="Compact atoms older than this many days.",
        ge=7, le=3650,
    )
    atom_type: Optional[str] = Field(
        default=None,
        description="Restrict to one atom type. Omit for all types.",
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "If True (default), show what WOULD happen without writing. "
            "Set False to apply compaction."
        ),
    )


class AtomsCompactTool(Tool[_CompactArgs]):
    """Compact old atoms by writing summary atoms and superseding originals.

    Groups active atoms by (type, YYYY-MM) for all months older than
    `before_days`. For each group, writes one summary atom listing all
    originals' summaries. Marks originals as superseded.
    Audit trail is always intact — originals are never deleted.

    dry_run=True (default) is safe; set dry_run=False to apply.
    """

    name = "atoms_compact"
    tier = 2
    description = (
        "Compact old atoms: write one summary atom per (type, month) group, "
        "then supersede the originals. Audit trail is intact — originals are never deleted. "
        "dry_run=True (default) is a safe preview; set dry_run=False to apply."
    )
    failure_modes = (
        "db_unavailable",
        "write_atom_unavailable",
        "dry_run_true_no_changes",
    )
    Args = _CompactArgs

    async def execute(self, args: _CompactArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        await asyncio.sleep(0)
        candidates = await asyncio.to_thread(_gather_candidates, args.before_days, args.atom_type)
        if not candidates:
            return ToolResult(ok=True, output={
                "compacted": 0,
                "message": (
                    f"No atoms older than {args.before_days} days"
                    + (f" of type '{args.atom_type}'" if args.atom_type else "")
                    + ". Nothing to compact."
                ),
            })

        groups = _group_by_type_month(candidates)

        if args.dry_run:
            return ToolResult(ok=True, output={
                "dry_run": True,
                "candidates": len(candidates),
                "groups": len(groups),
                "message": (
                    f"DRY RUN: would compact {len(candidates)} atoms into {len(groups)} "
                    f"summary atoms. Set dry_run=False to apply."
                ),
            })

        if open_atoms_db is None or write_atom is None:
            return ToolResult(ok=False, error="DB or write_atom unavailable — cannot compact.")

        results = await asyncio.to_thread(self._do_compact, candidates, groups, args.before_days)
        return ToolResult(ok=True, output=results)

    @staticmethod
    def _do_compact(candidates: list[dict], groups: dict, before_days: int) -> dict:
        conn = open_atoms_db()  # type: ignore[misc]
        now_iso = datetime.now(timezone.utc).isoformat()
        created_summaries = []

        try:
            for (atype, month), atoms in sorted(groups.items()):
                summaries = [
                    {"atom_id": a["atom_id"], "summary": a["summary"], "created_at": a["created_at"]}
                    for a in atoms
                ]
                summary_atom = write_atom(  # type: ignore[misc]
                    type="compaction-summary",
                    summary=(
                        f"Compacted {len(atoms)} '{atype}' atoms from {month} "
                        f"(older than {before_days} days)"
                    ),
                    content={
                        "original_type": atype,
                        "month": month,
                        "count": len(atoms),
                        "summaries": summaries,
                        "compacted_at": now_iso,
                    },
                    scope_tags=["compaction", atype, month],
                    created_by={"actor": "AtomsCompactTool", "version": __version__},
                )
                summary_id = summary_atom.get("atom_id", "") if isinstance(summary_atom, dict) else str(summary_atom)

                atom_ids = [a["atom_id"] for a in atoms]
                placeholders = ",".join("?" * len(atom_ids))
                conn.execute(
                    f"UPDATE atoms SET superseded_at = ?, superseded_by = ? "
                    f"WHERE atom_id IN ({placeholders})",
                    [now_iso, summary_id, *atom_ids],
                )
                conn.commit()
                created_summaries.append({"type": atype, "month": month, "count": len(atoms), "summary_id": summary_id})

        finally:
            conn.close()

        return {
            "compacted": len(candidates),
            "summary_atoms_created": len(created_summaries),
            "groups": created_summaries,
            "message": (
                f"Compacted {len(candidates)} atoms into {len(created_summaries)} summary atoms. "
                "Originals marked superseded. Audit trail intact."
            ),
        }


# ─── Status Tool (T0) ─────────────────────────────────────────────────────────

class _StatusArgs(BaseModel):
    pass


class AtomsCompactStatusTool(Tool[_StatusArgs]):
    """Check atoms store health via the AtomsCompactSentinel."""

    name = "atoms_compact_status"
    tier = 0
    description = (
        "Show atoms store health: total atom count, DB size, age distribution, "
        "and any compaction findings from the sentinel."
    )
    failure_modes = ("db_unavailable", "sentinel_not_registered")
    Args = _StatusArgs

    async def execute(self, args: _StatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        await asyncio.sleep(0)
        try:
            from sovereign_agent.stewardship.registry import instantiate
            sentinel = instantiate("atoms-compact")
            report = sentinel.scan()
            catalog = sentinel.load_catalog("default")
            stats = (catalog or {}).get("stats", {})
            findings = (catalog or {}).get("findings", [])

            return ToolResult(ok=True, output={
                "total": stats.get("total"),
                "active": stats.get("active"),
                "superseded": stats.get("superseded"),
                "superseded_pct": stats.get("superseded_pct"),
                "db_mb": stats.get("db_mb"),
                "oldest_at": stats.get("oldest_at"),
                "old_count": stats.get("old_count"),
                "old_days": stats.get("old_days", 90),
                "by_type": stats.get("by_type", {}),
                "findings": [
                    {"severity": f["severity"], "summary": f["summary"]}
                    for f in findings
                ],
                "health": report.summary,
            })
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"Could not run atoms-compact sentinel: {exc}")


__all__ = [
    "AtomsCompactPreviewTool",
    "AtomsCompactTool",
    "AtomsCompactStatusTool",
    "_gather_candidates",
    "_group_by_type_month",
]
