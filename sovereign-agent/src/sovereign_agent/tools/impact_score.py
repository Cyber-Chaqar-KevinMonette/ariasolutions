"""impact_score — Tier 0. Records an Impact Vector as a Knowledge Atom.

Called by the orchestrator during impact-score planner steps. Takes a list
of cell specifications (dimension, scale, score, confidence, notes), builds
an ImpactVector, and stores it as a Knowledge Atom in atoms.db.

Returns the atom_id of the newly created IV. Operator reviews via
`sov impact show <atom-id>`.

The tool VALIDATES every cell — score must be in [-1, 1], confidence in
[0, 1], dimension in {mental,physical,financial}, scale in
{micro,meso,macro,cosmic}. Invalid cells fail loud rather than getting
silently coerced.

Authority tier 0 — writing an IV atom doesn't apply any change. The IV
is information. Tier gating happens elsewhere (when an action is being
considered for execution, the IV's required_tier determines the approval
flow).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .base import Tool, ToolResult


class _CellSpec(BaseModel):
    """One cell of the IV."""
    dimension: Literal["mental", "physical", "financial"]
    scale: Literal["micro", "meso", "macro", "cosmic"]
    score: float = Field(ge=-1.0, le=1.0,
                         description="Signed magnitude. Negative = harm, positive = benefit.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0,
                              description="How sure? Be honest about uncertainty.")
    evidence_ref: str = Field(default="", max_length=200,
                              description="Optional: atom_id, URL, or path supporting the score.")
    notes: str = Field(default="", max_length=500,
                       description="Brief justification.")


class _Args(BaseModel):
    action_label: str = Field(min_length=1, max_length=200,
                              description="One-line summary of the action being scored.")
    cells: list[_CellSpec] = Field(min_length=1, max_length=12,
                                   description="1-12 cell specifications. Skip cells where you have no signal.")
    rationale: str = Field(default="", max_length=2000,
                           description="Overall reasoning for this IV.")
    parent_atom_id: str | None = Field(default=None,
                                        description="Optional: atom_id of the originating decision.")

    @field_validator("cells")
    @classmethod
    def _no_duplicate_cells(cls, v: list[_CellSpec]) -> list[_CellSpec]:
        seen: set[tuple[str, str]] = set()
        for c in v:
            key = (c.dimension, c.scale)
            if key in seen:
                raise ValueError(f"duplicate cell: {key!r}")
            seen.add(key)
        return v


class ImpactScoreTool(Tool[_Args]):
    name = "impact_score"
    tier = 0
    description = (
        "Record a multi-scale Impact Vector (3 dimensions × 4 scales) "
        "for an action as a Knowledge Atom. Stores 1-12 cells with score, "
        "confidence, and notes per cell. Returns the atom_id. "
        "Tier 0 — writing the IV doesn't enforce anything; it makes impact "
        "legible for operator review. FAILURE MODES: cell_validation; "
        "atom_storage_error."
    )
    failure_modes = (
        "cell_validation",
        "atom_storage_error",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from ..impact import ImpactCell, ImpactVector

        # Build the IV
        try:
            iv = ImpactVector(
                action_label=args.action_label,
                rationale=args.rationale,
            )
            for spec in args.cells:
                iv.set_cell(ImpactCell(
                    dimension=spec.dimension,
                    scale=spec.scale,
                    score=spec.score,
                    confidence=spec.confidence,
                    evidence_ref=spec.evidence_ref,
                    notes=spec.notes,
                ))
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"cell_validation: {type(e).__name__}: {e}")

        # Store as atom in atoms.db
        try:
            from ulid import ULID
            from ..db import open_atoms_db
            import json as _json
            atom_id = f"atom-iv-{ULID()}"
            atom_dict = iv.to_atom_dict(atom_id, parent_atom_id=args.parent_atom_id)

            conn = open_atoms_db()
            try:
                # The atoms.db schema expects content_ref + claims as JSON.
                conn.execute(
                    "INSERT INTO atoms(atom_id, type, summary, content_ref, "
                    "claims, parents, confidence, created_at, created_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        atom_id,
                        "decision",
                        atom_dict["summary"],
                        _json.dumps({"kind": "inline", "data": atom_dict["metadata"]}),
                        _json.dumps(atom_dict["claims"]),
                        _json.dumps(atom_dict["parents"]),
                        iv.aggregate_confidence(),
                        atom_dict.get("metadata", {}).get("created_at",
                            iv.created_at),
                        _json.dumps({"actor": "impact_score_tool", "trace_id": trace_id}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                ok=False,
                error=f"atom_storage_error: {type(e).__name__}: {e}",
            )

        # Build the result summary
        worst = iv.worst_cell()
        return ToolResult(
            ok=True,
            output=atom_id,
            metadata={
                "atom_id": atom_id,
                "action_label": iv.action_label,
                "cells_scored": len(iv.cells),
                "is": iv.aggregate_score(),
                "is_7g": iv.is_7g(),
                "confidence": iv.aggregate_confidence(),
                "required_tier": iv.required_tier(),
                "symbiosis_canary": iv.symbiosis_canary_tripped(),
                "seventh_gen_escalation": iv.seventh_gen_escalation(),
                "angels_advocate_flag": iv.angels_advocate_flag(),
                "worst_cell": (worst.predicate_key() if worst else None),
                "worst_score": (worst.score if worst else None),
            },
        )
