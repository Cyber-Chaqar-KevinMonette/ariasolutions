"""tools/lineage_tool.py — Identity lineage query (M75).

  lineage()   T0 — return Aria's founding atoms and milestone atoms in
                    chronological order (oldest first).

The birth record lives in the stewardship AtomStore (atoms.ndjson), not the
SQL atoms.db. Founding atoms are distilled identity claims, not operational
events — the L2 semantic layer is the right home for them.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _atom_store():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.atoms import AtomStore
    return AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")


class LineageTool(Tool):
    """Return Aria's founding atoms and milestone atoms in chronological order.

    Reads from the stewardship semantic atom store (atoms.ndjson). The
    founding atoms record when Aria was created, by whom, her purpose, her
    constitutional constraints, her co-creator, and her first milestones.

    Flags:
      birth_only=True   — only atoms tagged "founding"
      milestones=True   — only atoms tagged "milestone"
      (both off)        — all atoms tagged "birth-record" or "milestone"

    Returns each atom as: {atom_id, title, claim, ts_created, tags, evidence_refs}

    FAILURE MODES:
      atoms_store_missing — returns ok=True with empty list and a note
      no_birth_atoms_written_yet — returns ok=True with empty list and guidance
    """

    name = "lineage"
    tier = 0
    description = (
        "Return Aria's founding atoms and milestone atoms in chronological order "
        "(oldest first). birth_only=True returns only founding atoms. "
        "milestones=True returns only milestone atoms. "
        "Both flags off returns all birth-record and milestone atoms. "
        "When no atoms exist yet, returns empty list with guidance note."
    )
    failure_modes = ("atoms_store_missing", "no_birth_atoms_written_yet")

    class Args(BaseModel):
        birth_only: bool = Field(
            default=False,
            description="Return only atoms tagged 'founding'.",
        )
        milestones: bool = Field(
            default=False,
            description="Return only atoms tagged 'milestone'.",
        )
        tag: Optional[str] = Field(
            default=None,
            description="Filter by any specific tag (overrides birth_only/milestones).",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            store = _atom_store()
        except Exception as exc:
            return ToolResult(
                ok=True,
                output={"atoms": [], "count": 0, "note": f"atom store unavailable: {exc}"},
                metadata={"source": "lineage_tool"},
            )

        try:
            if args.tag is not None:
                atoms = store.search(tag=args.tag)
            elif args.birth_only:
                atoms = store.search(tag="founding")
            elif args.milestones:
                atoms = store.search(tag="milestone")
            else:
                # All birth-record OR milestone atoms
                birth = store.search(tag="birth-record")
                mile = store.search(tag="milestone")
                seen = set()
                merged = []
                for a in birth + mile:
                    if a.atom_id not in seen:
                        seen.add(a.atom_id)
                        merged.append(a)
                atoms = merged

            # Sort oldest-first (ts_created is ISO 8601, lexicographically sortable)
            atoms.sort(key=lambda a: a.ts_created)

            if not atoms:
                return ToolResult(
                    ok=True,
                    output={
                        "atoms": [],
                        "count": 0,
                        "note": (
                            "Birth record not yet written. "
                            "Run the founding_atoms.py script via apply_birth_records.sh."
                        ),
                    },
                    metadata={"source": "lineage_tool"},
                )

            records = [
                {
                    "atom_id": a.atom_id,
                    "title": a.title,
                    "claim": a.claim,
                    "kind": str(a.kind),
                    "confidence": a.confidence,
                    "channels": a.channels,
                    "tags": a.tags,
                    "evidence_refs": a.evidence_refs,
                    "ts_created": a.ts_created,
                }
                for a in atoms
            ]

            summary_lines = [f"  • {r['title']}" for r in records]
            summary = "\n".join(summary_lines)

            return ToolResult(
                ok=True,
                output={
                    "atoms": records,
                    "count": len(records),
                    "summary": summary,
                },
                metadata={"source": "lineage_tool", "total": len(records)},
            )

        except Exception as exc:
            return ToolResult(
                ok=True,
                output={"atoms": [], "count": 0, "note": f"search failed: {exc}"},
                metadata={"source": "lineage_tool"},
            )
