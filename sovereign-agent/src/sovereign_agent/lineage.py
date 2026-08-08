"""
╔══════════════════════════════════════════════════════════════════════════╗
║  lineage.py — Provenance traversal for atoms / closets / triples         ║
║  v0.2.11+                                                                ║
║                                                                          ║
║  Every layer of the system records WHERE its content came from:          ║
║                                                                          ║
║    atoms.db                                                              ║
║      └── atom.parents       — atom_ids that produced this atom (e.g.    ║
║                                a distilled atom listing its sources)     ║
║      └── atom.content_ref   — source file path (for ingested atoms)     ║
║                                                                          ║
║    palace.db                                                             ║
║      └── closet.atom_ids    — atom_ids that contributed to this closet  ║
║      └── triple.source_atom_ids                                          ║
║      └── triple.source_closet_id                                         ║
║                                                                          ║
║  This module follows those breadcrumbs in both directions:               ║
║                                                                          ║
║    forward:  source_file → atom → closet → triples / insights           ║
║    reverse:  closet → atoms → source files                              ║
║                                                                          ║
║  Used by `sov palace lineage <id>` and the `lineage_search` tool.       ║
║                                                                          ║
║  Pure read-only traversal. No mutations. Safe to call on any palace     ║
║  state.                                                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass
class AtomNode:
    """Lightweight view of an atom for lineage rendering."""
    atom_id: str
    atom_type: str
    summary: str
    parents: list[str] = field(default_factory=list)
    source_file: str | None = None
    created_at: str = ""


@dataclass
class ClosetNode:
    """Lightweight view of a closet for lineage rendering."""
    closet_id: str
    room_id: str
    topic: str
    atom_ids: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


@dataclass
class TripleNode:
    """Lightweight view of a triple for lineage rendering."""
    triple_id: str
    subject_id: str
    predicate: str
    object_id: str | None
    object_literal: str | None
    confidence: float
    source_atom_ids: list[str] = field(default_factory=list)
    source_closet_id: str | None = None


@dataclass
class LineageForward:
    """Forward chain starting from an atom_id.

    ``source → atom → closets → triples → child_atoms``.
    """
    atom: AtomNode | None = None
    parents: list[AtomNode] = field(default_factory=list)
    closets: list[ClosetNode] = field(default_factory=list)
    triples: list[TripleNode] = field(default_factory=list)
    children: list[AtomNode] = field(default_factory=list)  # atoms whose 'parents' include this atom


@dataclass
class LineageReverse:
    """Back-chain starting from a closet_id.

    ``closet → contributing atoms → source files``.
    """
    closet: ClosetNode | None = None
    atoms: list[AtomNode] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    triples_sourced_from: list[TripleNode] = field(default_factory=list)


# ─── Atom helpers ───────────────────────────────────────────────────────────


def _atom_node_from_row(row: tuple) -> AtomNode:
    """Build AtomNode from atoms.db row.

    Row order matches:
      atom_id, type, summary, content_ref, parents, created_at
    """
    atom_id, atype, summary, content_ref_json, parents_json, created_at = row[:6]

    # content_ref is JSON; pull source_file if present
    source_file = None
    try:
        ref = json.loads(content_ref_json) if content_ref_json else {}
        if isinstance(ref, dict):
            source_file = ref.get("source_file") or ref.get("path")
    except json.JSONDecodeError:
        pass

    parents: list[str] = []
    try:
        parents = json.loads(parents_json) if parents_json else []
        if not isinstance(parents, list):
            parents = []
    except json.JSONDecodeError:
        parents = []

    return AtomNode(
        atom_id=str(atom_id),
        atom_type=str(atype) if atype else "",
        summary=str(summary or "")[:500],  # cap for display
        parents=[str(p) for p in parents if p],
        source_file=str(source_file) if source_file else None,
        created_at=str(created_at) if created_at else "",
    )


def get_atom_by_id(atom_id: str) -> AtomNode | None:
    """Read one atom by id. Returns None if not found."""
    from .db import open_atoms_db
    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT atom_id, type, summary, content_ref, parents, created_at "
            "FROM atoms WHERE atom_id = ?",
            (atom_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _atom_node_from_row(tuple(row))


def find_child_atoms(atom_id: str, *, limit: int = 50) -> list[AtomNode]:
    """Find atoms whose `parents` includes the given atom_id.

    parents is stored as JSON, so we LIKE-match. False positives are
    possible if an atom_id is a substring of another — we filter post-fetch.
    """
    from .db import open_atoms_db
    conn = open_atoms_db()
    try:
        # LIKE pattern wraps atom_id in quotes to reduce substring matches
        pattern = f'%"{atom_id}"%'
        rows = conn.execute(
            "SELECT atom_id, type, summary, content_ref, parents, created_at "
            "FROM atoms WHERE parents LIKE ? LIMIT ?",
            (pattern, limit * 2),  # over-fetch then filter
        ).fetchall()
    finally:
        conn.close()
    out: list[AtomNode] = []
    for r in rows:
        node = _atom_node_from_row(tuple(r))
        # Filter: confirm atom_id is genuinely in parents (post-JSON-parse)
        if atom_id in node.parents:
            out.append(node)
            if len(out) >= limit:
                break
    return out


# ─── Closet/Triple helpers ──────────────────────────────────────────────────


def _closet_node_from_row(row) -> ClosetNode:
    return ClosetNode(
        closet_id=row["id"],
        room_id=row["room_id"],
        topic=row["topic"] or "",
        atom_ids=[a for a in (row["atom_ids"] or "").split(",") if a],
        entities=[e for e in (row["entities"] or "").split(";") if e],
    )


def _triple_node_from_row(row) -> TripleNode:
    return TripleNode(
        triple_id=row["id"],
        subject_id=row["subject_id"],
        predicate=row["predicate"],
        object_id=row["object_id"],
        object_literal=row["object_literal"],
        confidence=row["confidence"] or 0.0,
        source_atom_ids=[a for a in (row["source_atom_ids"] or "").split(",") if a],
        source_closet_id=row["source_closet_id"],
    )


def get_closet_by_id(closet_id: str) -> ClosetNode | None:
    """Read one closet by id."""
    from .palace import open_palace
    palace = open_palace()
    try:
        with palace._connect() as c:
            row = c.execute(
                "SELECT * FROM closets WHERE id = ?", (closet_id,),
            ).fetchone()
    finally:
        palace.close()
    return _closet_node_from_row(row) if row else None


def find_closets_referencing_atom(atom_id: str) -> list[ClosetNode]:
    """Closets whose atom_ids contains this atom."""
    from .palace import open_palace
    palace = open_palace()
    try:
        with palace._connect() as c:
            rows = c.execute(
                "SELECT * FROM closets WHERE atom_ids LIKE ?",
                (f"%{atom_id}%",),
            ).fetchall()
    finally:
        palace.close()
    out = []
    for r in rows:
        node = _closet_node_from_row(r)
        # Filter: atom_id genuinely in the parsed list
        if atom_id in node.atom_ids:
            out.append(node)
    return out


def find_triples_sourced_from_atom(atom_id: str) -> list[TripleNode]:
    """Triples whose source_atom_ids includes this atom."""
    from .palace import open_palace
    palace = open_palace()
    try:
        with palace._connect() as c:
            rows = c.execute(
                "SELECT * FROM triples WHERE source_atom_ids LIKE ?",
                (f"%{atom_id}%",),
            ).fetchall()
    finally:
        palace.close()
    out = []
    for r in rows:
        node = _triple_node_from_row(r)
        if atom_id in node.source_atom_ids:
            out.append(node)
    return out


def find_triples_sourced_from_closet(closet_id: str) -> list[TripleNode]:
    """Triples whose source_closet_id == this closet."""
    from .palace import open_palace
    palace = open_palace()
    try:
        with palace._connect() as c:
            rows = c.execute(
                "SELECT * FROM triples WHERE source_closet_id = ?",
                (closet_id,),
            ).fetchall()
    finally:
        palace.close()
    return [_triple_node_from_row(r) for r in rows]


# ─── Top-level traversal ────────────────────────────────────────────────────


def lineage_forward(atom_id: str) -> LineageForward:
    """Walk forward from an atom: parents, closets, triples, child atoms.

    All read-only. Returns a LineageForward bundle suitable for rendering.
    """
    atom = get_atom_by_id(atom_id)
    if atom is None:
        return LineageForward(atom=None)

    parents: list[AtomNode] = []
    for parent_id in atom.parents:
        p = get_atom_by_id(parent_id)
        if p is not None:
            parents.append(p)

    closets = find_closets_referencing_atom(atom_id)
    triples = find_triples_sourced_from_atom(atom_id)
    children = find_child_atoms(atom_id)

    return LineageForward(
        atom=atom,
        parents=parents,
        closets=closets,
        triples=triples,
        children=children,
    )


def lineage_reverse(closet_id: str) -> LineageReverse:
    """Walk back from a closet: contributing atoms → source files.

    Also surfaces triples sourced from this closet for completeness.
    """
    closet = get_closet_by_id(closet_id)
    if closet is None:
        return LineageReverse(closet=None)

    atoms: list[AtomNode] = []
    source_files: list[str] = []
    seen_files: set[str] = set()
    for aid in closet.atom_ids:
        a = get_atom_by_id(aid)
        if a is None:
            continue
        atoms.append(a)
        if a.source_file and a.source_file not in seen_files:
            source_files.append(a.source_file)
            seen_files.add(a.source_file)

    triples = find_triples_sourced_from_closet(closet_id)

    return LineageReverse(
        closet=closet,
        atoms=atoms,
        source_files=source_files,
        triples_sourced_from=triples,
    )


# ─── Markdown rendering ────────────────────────────────────────────────────


def render_forward_markdown(lf: LineageForward) -> str:
    """Render forward lineage as a navigable markdown tree."""
    if lf.atom is None:
        return "(atom not found)"
    parts: list[str] = []
    parts.append(f"# Lineage: forward chain\n")
    parts.append(f"## Atom\n")
    parts.append(f"- **id:** `{lf.atom.atom_id}`\n")
    parts.append(f"- **type:** {lf.atom.atom_type}\n")
    if lf.atom.source_file:
        parts.append(f"- **source file:** `{lf.atom.source_file}`\n")
    parts.append(f"- **created:** {lf.atom.created_at}\n")
    parts.append(f"- **summary:** {lf.atom.summary[:300]}\n\n")

    if lf.parents:
        parts.append(f"## Parents (this atom was derived from {len(lf.parents)})\n")
        for p in lf.parents:
            parts.append(f"- `{p.atom_id}` — {p.summary[:100]}\n")
        parts.append("\n")

    if lf.closets:
        parts.append(f"## Closets containing this atom ({len(lf.closets)})\n")
        for c in lf.closets:
            parts.append(f"- `{c.closet_id}` (room: {c.room_id})\n")
            parts.append(f"  - topic: {c.topic[:120]}\n")
        parts.append("\n")

    if lf.triples:
        parts.append(f"## Triples sourced from this atom ({len(lf.triples)})\n")
        for t in lf.triples:
            obj = t.object_id or t.object_literal or "?"
            parts.append(f"- `{t.triple_id}` · {t.subject_id} —[{t.predicate}]→ {obj} (conf={t.confidence:.2f})\n")
        parts.append("\n")

    if lf.children:
        parts.append(f"## Child atoms (derived from this one) ({len(lf.children)})\n")
        for ch in lf.children:
            parts.append(f"- `{ch.atom_id}` — {ch.summary[:100]}\n")
        parts.append("\n")

    if not (lf.parents or lf.closets or lf.triples or lf.children):
        parts.append("_No upstream parents, downstream children, or palace structure for this atom._\n")
        parts.append("_Either it's a leaf atom or palace-mine hasn't been run yet._\n")

    return "".join(parts)


def render_reverse_markdown(lr: LineageReverse) -> str:
    """Render reverse lineage as a navigable markdown tree."""
    if lr.closet is None:
        return "(closet not found)"
    parts: list[str] = []
    parts.append(f"# Lineage: reverse chain\n")
    parts.append(f"## Closet\n")
    parts.append(f"- **id:** `{lr.closet.closet_id}`\n")
    parts.append(f"- **room:** {lr.closet.room_id}\n")
    parts.append(f"- **topic:** {lr.closet.topic}\n")
    if lr.closet.entities:
        parts.append(f"- **entities:** {', '.join(lr.closet.entities[:10])}\n")
    parts.append("\n")

    if lr.atoms:
        parts.append(f"## Contributing atoms ({len(lr.atoms)})\n")
        for a in lr.atoms:
            parts.append(f"- `{a.atom_id}` ({a.atom_type})\n")
            if a.source_file:
                parts.append(f"  - source: `{a.source_file}`\n")
            parts.append(f"  - {a.summary[:160]}\n")
        parts.append("\n")
    else:
        parts.append("_No contributing atoms — closet may be doctrine (e.g., MOS canon)._\n\n")

    if lr.source_files:
        parts.append(f"## Source files ({len(lr.source_files)})\n")
        for f in lr.source_files:
            parts.append(f"- `{f}`\n")
        parts.append("\n")

    if lr.triples_sourced_from:
        parts.append(f"## Triples derived from this closet ({len(lr.triples_sourced_from)})\n")
        for t in lr.triples_sourced_from:
            obj = t.object_id or t.object_literal or "?"
            parts.append(f"- `{t.triple_id}` · {t.subject_id} —[{t.predicate}]→ {obj}\n")
        parts.append("\n")

    return "".join(parts)


def lineage_to_dict(lf: LineageForward | LineageReverse) -> dict:
    """JSON-serializable view for --json output."""
    if isinstance(lf, LineageForward):
        return {
            "direction": "forward",
            "atom": _node_to_dict(lf.atom) if lf.atom else None,
            "parents": [_node_to_dict(p) for p in lf.parents],
            "closets": [_node_to_dict(c) for c in lf.closets],
            "triples": [_node_to_dict(t) for t in lf.triples],
            "children": [_node_to_dict(ch) for ch in lf.children],
        }
    else:
        return {
            "direction": "reverse",
            "closet": _node_to_dict(lf.closet) if lf.closet else None,
            "atoms": [_node_to_dict(a) for a in lf.atoms],
            "source_files": lf.source_files,
            "triples_sourced_from": [_node_to_dict(t) for t in lf.triples_sourced_from],
        }


def _node_to_dict(node: Any) -> dict:
    """Generic dataclass → dict."""
    from dataclasses import asdict
    return asdict(node) if node is not None else {}
