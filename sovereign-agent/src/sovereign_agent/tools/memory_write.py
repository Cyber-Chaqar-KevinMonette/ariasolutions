"""memory_write — Tier 1.

Writes an Atom into ``atoms.db``. This is the primary way the agent
accumulates durable knowledge. Memory writes don't touch the filesystem
beyond the atoms.db file, so the path guard doesn't apply — but the schema
validation (``Atom.__post_init__``) is its own gate: every atom MUST have
parents (event ULIDs), confidence in [0,1], and summary ≤1000 chars.
"""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..db import open_atoms_db
from ..memory import Atom, index_atom_vector, write_atom
from .base import Tool, ToolResult


class _Args(BaseModel):
    type: str = Field(
        description="Atom type (e.g., 'doc', 'snippet', 'decision', 'observation')"
    )
    summary: str = Field(
        max_length=1000,
        description="One-line summary of what this atom captures (≤1000 chars)",
    )
    content: str = Field(
        description="Full content. Stored inline if small; spilled to blob otherwise."
    )
    parents: list[str] = Field(
        min_length=1,
        description="Event ULIDs that produced this atom — required for provenance",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence 0..1 — be honest, 1.0 only with strong evidence"
    )
    claims: list[dict] = Field(
        default_factory=list,
        description="Optional list of {text, evidence_ref} claim entries",
    )
    scope_path: str | None = Field(default=None, description="Optional scope (path/topic)")
    scope_tags: list[str] = Field(default_factory=list)


class MemoryWriteTool(Tool[_Args]):
    name = "memory_write"
    tier = 1
    description = (
        "Persist an atom (semantic memory unit) to atoms.db. Use this to record "
        "decisions, observations, distilled facts, and learned conventions for "
        "future runs to retrieve. Append-only: never overwrites; use memory_extend "
        "to revise. FAILURE MODES: schema violation (parents empty, confidence "
        "out of range, summary too long); DB locked; disk full."
    )
    failure_modes = (
        "schema_violation",
        "db_locked",
        "disk_full",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            atom = Atom(
                type=args.type,
                summary=args.summary,
                content_ref={"kind": "inline", "content": args.content},
                claims=args.claims,
                parents=args.parents,
                confidence=args.confidence,
                created_by={
                    "actor": "agent",
                    "model": SETTINGS.orchestrator_model,
                    "version": "0.2.1",
                },
                scope_path=args.scope_path,
                scope_tags=args.scope_tags,
            )
        except ValueError as e:
            return ToolResult(ok=False, error=f"schema violation: {e}")

        # Off-thread DB write — sqlite calls are blocking. write_atom()
        # itself now also indexes into fts_atoms (found live 2026-08-02,
        # see memory/atom.py's write_atom docstring) — this used to be a
        # completely dead search path.
        def _write() -> str:
            conn = open_atoms_db()
            try:
                aid = write_atom(conn, atom)
                conn.commit()
                return aid
            finally:
                conn.close()

        try:
            atom_id = await asyncio.to_thread(_write)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"db write failed: {e}")

        vector_indexed = False
        try:
            vconn = open_atoms_db()
            try:
                await index_atom_vector(vconn, atom)
                vconn.commit()
                vector_indexed = True
            finally:
                vconn.close()
        except Exception:  # noqa: BLE001 — embedding/Ollama down: FTS-only is still searchable
            vector_indexed = False

        return ToolResult(
            ok=True,
            output={"atom_id": atom_id, "version": atom.version, "vector_indexed": vector_indexed},
            metadata={"atom_id": atom_id},
        )
