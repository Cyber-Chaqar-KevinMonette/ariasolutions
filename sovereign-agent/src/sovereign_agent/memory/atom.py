"""Atom — the durable unit of semantic memory.

Architecture §8 + MOS §14. Append-only with version chains.

The version-chain pattern is ported from mos_knowledge.py: extending an atom
NEVER mutates the parent. It writes a new row with version=parent.version+1
and parent_atom_id=parent.atom_id. The parent is marked `superseded_at` so
queries can ask for "head of chain" cheaply, but its row is preserved
verbatim. This gives full lineage for forensics and rollback by simply
reading older versions.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ulid import ULID


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Atom:
    """One unit of semantic memory. Schema-validated on construction."""

    type: str                                   # MOS §14 enum (e.g., "doc", "snippet", "decision")
    summary: str                                # ≤1000 chars
    content_ref: dict[str, Any]                 # {"kind": "blob"|"file"|"inline", ...}
    claims: list[dict[str, str]]                # [{"text": ..., "evidence_ref": ...}]
    parents: list[str]                          # event ULIDs
    confidence: float                           # 0..1
    created_by: dict[str, Any]                  # {"actor": ..., "model": ..., "version": ...}
    scope_path: str | None = None
    scope_tags: list[str] = field(default_factory=list)
    policy: str = "local_only"
    atom_id: str = field(default_factory=lambda: str(ULID()))
    version: int = 1
    parent_atom_id: str | None = None
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if len(self.summary) > 1000:
            raise ValueError(f"summary too long: {len(self.summary)} > 1000")
        if not self.parents:
            # MOS: every atom must trace to evidence. v0.1+ enforces non-empty.
            raise ValueError("atom must have at least one parent event ULID")
        if self.version < 1:
            raise ValueError(f"version must be >= 1, got {self.version}")
        if self.version > 1 and self.parent_atom_id is None:
            raise ValueError("atoms with version > 1 must have parent_atom_id set")


def write_atom(conn: sqlite3.Connection, atom: Atom) -> str:
    """Insert atom into atoms.db. Returns atom_id.

    Append-only: this never updates an existing row. To create a new version
    of an atom, use ``extend_atom`` instead.

    Also indexes into fts_atoms (found live 2026-08-02: this write path
    had NEVER populated either search index — sql/002_atoms.sql's own
    comment says vec_atoms is "populated after embedding model runs," but
    nothing in the codebase ever actually did that for FTS or vector,
    across all ~11 call sites. Every atom ever written was permanently
    unsearchable via memory_search. FTS indexing is synchronous and free
    of external calls, so it belongs HERE — one fix covers every caller,
    not just the ones with an async context available. Vector indexing
    needs a real embedding-model call, so it stays an opt-in extra step
    for async callers — see memory/retrieval.py's index_atom_vector."""
    conn.execute(
        "INSERT INTO atoms ("
        "atom_id, type, scope_path, scope_tags, summary, content_ref, "
        "claims, parents, version, parent_atom_id, policy, confidence, "
        "created_at, created_by"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            atom.atom_id,
            atom.type,
            atom.scope_path,
            json.dumps(atom.scope_tags, sort_keys=True),
            atom.summary,
            json.dumps(atom.content_ref, sort_keys=True),
            json.dumps(atom.claims, sort_keys=True),
            json.dumps(atom.parents, sort_keys=True),
            atom.version,
            atom.parent_atom_id,
            atom.policy,
            atom.confidence,
            atom.created_at,
            json.dumps(atom.created_by, sort_keys=True),
        ),
    )
    content = atom.content_ref.get("content", "") if atom.content_ref.get("kind") == "inline" else ""
    conn.execute(
        "INSERT INTO fts_atoms (atom_id, summary, content) VALUES (?, ?, ?)",
        (atom.atom_id, atom.summary, content),
    )
    return atom.atom_id


def extend_atom(
    conn: sqlite3.Connection,
    *,
    parent_atom_id: str,
    summary: str,
    content_ref: dict[str, Any],
    claims: list[dict[str, str]],
    parents: list[str],
    confidence: float,
    created_by: dict[str, Any],
) -> str:
    """Create a new version of an existing atom.

    The parent row is NEVER modified beyond setting ``superseded_at`` /
    ``superseded_by`` — its content remains for forensic reads. The new atom
    inherits ``type``, ``scope_path``, ``scope_tags``, and ``policy`` from
    the parent unless you write directly via ``write_atom``.

    Returns the new atom_id.
    """
    parent_row = conn.execute(
        "SELECT type, scope_path, scope_tags, policy, version FROM atoms WHERE atom_id = ?",
        (parent_atom_id,),
    ).fetchone()
    if parent_row is None:
        raise ValueError(f"parent atom not found: {parent_atom_id}")

    p_type, p_scope_path, p_scope_tags_json, p_policy, p_version = parent_row
    new_version = (p_version or 1) + 1

    new_atom = Atom(
        type=p_type,
        summary=summary,
        content_ref=content_ref,
        claims=claims,
        parents=parents,
        confidence=confidence,
        created_by=created_by,
        scope_path=p_scope_path,
        scope_tags=json.loads(p_scope_tags_json) if p_scope_tags_json else [],
        policy=p_policy,
        version=new_version,
        parent_atom_id=parent_atom_id,
    )
    new_id = write_atom(conn, new_atom)

    # Mark parent as superseded — but keep its row intact
    conn.execute(
        "UPDATE atoms SET superseded_at = ?, superseded_by = ? WHERE atom_id = ?",
        (_utc_now(), new_id, parent_atom_id),
    )
    return new_id


def get_atom(conn: sqlite3.Connection, atom_id: str) -> dict[str, Any] | None:
    """Fetch one atom row as a dict, or None."""
    cur = conn.execute("SELECT * FROM atoms WHERE atom_id = ?", (atom_id,))
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def head_of_chain(conn: sqlite3.Connection, atom_id: str) -> str:
    """Walk forward through ``superseded_by`` to the latest version."""
    current = atom_id
    seen: set[str] = set()
    while True:
        if current in seen:
            raise RuntimeError(f"cycle detected in atom chain at {current}")
        seen.add(current)
        row = conn.execute(
            "SELECT superseded_by FROM atoms WHERE atom_id = ?", (current,)
        ).fetchone()
        if row is None:
            raise ValueError(f"atom not found: {current}")
        if row[0] is None:
            return current
        current = row[0]
