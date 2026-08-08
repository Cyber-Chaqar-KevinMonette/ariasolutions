"""
╔══════════════════════════════════════════════════════════════════════════╗
║  provenance.py — walk backward through everything that informed X        ║
║  v0.2.18.0                                                                ║
║                                                                           ║
║  Aria's memory has many pointers: atoms supersede atoms, recalls cite   ║
║  atoms, tasks link recalls and atoms, facts have source events. Until  ║
║  now, these pointers were navigated piecemeal by each channel.         ║
║                                                                           ║
║  Provenance unifies the walk. Given any node (atom, fact, recall,      ║
║  task, episode, etc.), it returns the directed acyclic graph of every  ║
║  upstream node that contributed to it, with edge labels naming the    ║
║  relationship.                                                          ║
║                                                                           ║
║  "Show your work" becomes a one-call operation. Aria can produce a    ║
║  rendered tree of evidence behind any conclusion she states.          ║
║                                                                           ║
║  HOW IT'S BUILT                                                          ║
║                                                                           ║
║    A registry of edge-extractors. Each extractor is a function:        ║
║                                                                           ║
║      extractor(conn, node_id) -> list[(target_node_id, edge_label)]   ║
║                                                                           ║
║    Built-in extractors cover the v0.2.18 schema. New channels register ║
║    extractors that describe how their rows point at upstream nodes.   ║
║                                                                           ║
║    ``walk_backward(conn, node_id, max_depth=...)`` traverses the      ║
║    union of every registered extractor's edges, with cycle detection. ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable


# An extractor returns the list of (upstream_node_id, edge_label) pairs
# that flow INTO ``node_id``. The node_id is opaque — it could be an
# atom_id, fact_id, recall_id, etc. The extractor decides how to look it up.
Extractor = Callable[[sqlite3.Connection, str], list[tuple[str, str]]]


_EXTRACTORS: list[Extractor] = []


def register_extractor(extractor: Extractor) -> None:
    if extractor not in _EXTRACTORS:
        _EXTRACTORS.append(extractor)


# ─── Built-in extractors ──────────────────────────────────────────────────


def _atom_parents(conn: sqlite3.Connection, node_id: str) -> list[tuple[str, str]]:
    """If node_id is an atom, return its parent_atom_id (supersedes chain)
    and any parents listed in the ``parents`` JSON array."""
    row = conn.execute(
        "SELECT parent_atom_id, parents FROM atoms WHERE atom_id = ?",
        (node_id,),
    ).fetchone()
    if row is None:
        return []
    out: list[tuple[str, str]] = []
    if row[0]:
        out.append((row[0], "supersedes"))
    try:
        import json
        parents = json.loads(row[1] or "[]")
        for p in parents:
            if isinstance(p, str):
                out.append((p, "claims_parent"))
    except (ValueError, TypeError):
        pass
    return out


def _fact_source(conn: sqlite3.Connection, node_id: str) -> list[tuple[str, str]]:
    """If node_id is a people_facts.fact_id, return its source_event_id and atom."""
    if not _table_exists(conn, "people_facts"):
        return []
    row = conn.execute(
        "SELECT source_event_id, atom_id FROM people_facts WHERE fact_id = ?",
        (node_id,),
    ).fetchone()
    if row is None:
        return []
    out: list[tuple[str, str]] = []
    if row[0]:
        out.append((row[0], "source_event"))
    if row[1]:
        out.append((row[1], "atom"))
    return out


def _recall_sources(conn: sqlite3.Connection, node_id: str) -> list[tuple[str, str]]:
    """If node_id is a recall_id, return all its recall_sources."""
    if not _table_exists(conn, "recall_sources"):
        return []
    rows = conn.execute(
        "SELECT source_kind, source_id FROM recall_sources WHERE recall_id = ?",
        (node_id,),
    ).fetchall()
    out: list[tuple[str, str]] = []
    for kind, sid in rows:
        out.append((sid, f"recall_source/{kind}"))

    # Also walk supersedes chain
    sup = conn.execute(
        "SELECT supersedes FROM recalls WHERE recall_id = ?", (node_id,)
    ).fetchone()
    if sup and sup[0]:
        out.append((sup[0], "supersedes_recall"))

    # Atom companion
    atm = conn.execute(
        "SELECT atom_id FROM recalls WHERE recall_id = ?", (node_id,)
    ).fetchone()
    if atm and atm[0]:
        out.append((atm[0], "companion_atom"))
    return out


def _task_links(conn: sqlite3.Connection, node_id: str) -> list[tuple[str, str]]:
    """If node_id is a task_id, return its parent task, linked atoms and recalls."""
    if not _table_exists(conn, "task_records"):
        return []
    row = conn.execute(
        "SELECT parent_task_id, related_atom_ids, related_recall_ids, atom_id "
        "FROM task_records WHERE task_id = ?",
        (node_id,),
    ).fetchone()
    if row is None:
        return []
    out: list[tuple[str, str]] = []
    if row[0]:
        out.append((row[0], "parent_task"))
    if row[3]:
        out.append((row[3], "companion_atom"))
    try:
        import json
        for a in json.loads(row[1] or "[]"):
            if isinstance(a, str):
                out.append((a, "task_atom"))
        for r in json.loads(row[2] or "[]"):
            if isinstance(r, str):
                out.append((r, "task_recall"))
    except (ValueError, TypeError):
        pass
    return out


def _episode_members(conn: sqlite3.Connection, node_id: str) -> list[tuple[str, str]]:
    """If node_id is an episode_id, return its members (which it 'contains',
    i.e. points downstream — but we record this for navigability)."""
    if not _table_exists(conn, "episode_members"):
        return []
    rows = conn.execute(
        "SELECT member_kind, member_ref FROM episode_members WHERE episode_id = ?",
        (node_id,),
    ).fetchall()
    return [(ref, f"episode_member/{kind}") for kind, ref in rows]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


# Register built-ins on import
for _ex in (_atom_parents, _fact_source, _recall_sources, _task_links,
            _episode_members):
    register_extractor(_ex)


# ─── Graph types ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProvenanceEdge:
    source: str       # upstream node (parent)
    target: str       # the node being explained (child)
    label: str        # relationship


@dataclass
class ProvenanceGraph:
    root: str
    nodes: set[str] = field(default_factory=set)
    edges: list[ProvenanceEdge] = field(default_factory=list)
    truncated: bool = False
    max_depth_reached: int = 0

    def upstream_of(self, node: str) -> list[ProvenanceEdge]:
        return [e for e in self.edges if e.target == node]

    def render(self) -> str:
        if not self.nodes:
            return f"provenance of {self.root}: (none — node may not exist)"
        lines = [f"provenance of {self.root}:"]
        seen: set[str] = set()

        def walk(node: str, depth: int) -> None:
            if depth > 10 or node in seen:
                return
            seen.add(node)
            for edge in self.upstream_of(node):
                indent = "  " * (depth + 1)
                lines.append(f"{indent}↑ [{edge.label}] {edge.source}")
                walk(edge.source, depth + 1)

        walk(self.root, 0)
        if self.truncated:
            lines.append(f"  (truncated at depth {self.max_depth_reached})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "nodes": sorted(self.nodes),
            "edges": [
                {"source": e.source, "target": e.target, "label": e.label}
                for e in self.edges
            ],
            "truncated": self.truncated,
            "max_depth_reached": self.max_depth_reached,
        }


# ─── Walker ──────────────────────────────────────────────────────────────


def walk_backward(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    max_depth: int = 20,
    max_nodes: int = 500,
) -> ProvenanceGraph:
    """Build the upstream-provenance graph for ``node_id``.

    Walks every registered extractor's edges, deduplicates, detects
    cycles, and bounds total work via max_depth and max_nodes. The
    result is a directed acyclic graph (cycles are short-circuited).
    """
    graph = ProvenanceGraph(root=node_id)
    graph.nodes.add(node_id)

    frontier: list[tuple[str, int]] = [(node_id, 0)]
    visited: set[str] = {node_id}

    while frontier:
        current, depth = frontier.pop(0)
        graph.max_depth_reached = max(graph.max_depth_reached, depth)
        if depth >= max_depth:
            graph.truncated = True
            continue
        if len(graph.nodes) >= max_nodes:
            graph.truncated = True
            break

        for extractor in _EXTRACTORS:
            try:
                edges = extractor(conn, current)
            except sqlite3.OperationalError:
                # Channel's tables may not exist in test fixtures
                continue
            except Exception:
                continue
            for upstream, label in edges:
                if upstream is None or upstream == "":
                    continue
                graph.edges.append(ProvenanceEdge(
                    source=upstream, target=current, label=label,
                ))
                if upstream not in visited:
                    visited.add(upstream)
                    graph.nodes.add(upstream)
                    frontier.append((upstream, depth + 1))

    return graph


def get_extractors() -> list[Extractor]:
    """Return registered extractors (read-only)."""
    return list(_EXTRACTORS)


__all__ = [
    "ProvenanceEdge", "ProvenanceGraph",
    "walk_backward", "register_extractor", "get_extractors",
    "Extractor",
]
