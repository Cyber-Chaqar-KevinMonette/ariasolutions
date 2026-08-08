"""
╔══════════════════════════════════════════════════════════════════════════╗
║  memory_namespaces.py — Per-project memory scoping                       ║
║  v0.2.13                                                                  ║
║                                                                           ║
║  Atoms have a ``scope_tags`` JSON column (existing v0.2.x). This module  ║
║  adds first-class project-namespacing on top: every atom CAN be tagged   ║
║  with one or more project names, and memory_search CAN filter to a      ║
║  specific project to scope retrieval.                                    ║
║                                                                           ║
║  Why "can," not "must"? The default behavior is unchanged. Atoms not     ║
║  tagged with any project are visible globally (matching v0.2.12). Atoms  ║
║  tagged with a project are visible (a) globally AND (b) when explicitly  ║
║  filtered to that project. This is additive, not exclusive — a project   ║
║  scope is a hint to retrieval, not a wall.                              ║
║                                                                           ║
║  USAGE:                                                                  ║
║                                                                           ║
║    # When dream is tied to a project, atomize tags every cycle output    ║
║    # with that project's name. Architect, ideate, build steps all read   ║
║    # the same tag.                                                       ║
║    tag_atom(conn, atom_id="atom-...", project="genesis-seeds")           ║
║                                                                           ║
║    # When the dream-builder's ideate step searches for prior work, it    ║
║    # passes the project to scope retrieval.                              ║
║    search_in_project(conn, query="trillion-dollar idea",                  ║
║                       project="genesis-seeds", query_vec=...)            ║
║                                                                           ║
║  THE PROJECT-SCOPED MEMORY GIVES EACH DREAM A FOCUS. Without it, a        ║
║  long-running operator with multiple dreams sees their themes bleed      ║
║  into each other through memory_search. With it, each dream's lineage   ║
║  is clean.                                                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any


# Project names use the same alphabet as project YAML filenames — keep
# the two namespaces aligned to avoid surprises.
_VALID_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,63}$")


def is_valid_project_name(name: str) -> bool:
    """Project names: alphanum, dash, dot, underscore. ≤64 chars. Non-empty."""
    return bool(_VALID_PROJECT_NAME_RE.match(name or ""))


def normalize_project_name(name: str) -> str:
    """Return name unchanged if valid, else raise ValueError.

    Centralized here so every namespace touchpoint validates the same way.
    """
    name = (name or "").strip()
    if not is_valid_project_name(name):
        raise ValueError(
            f"invalid project name {name!r}; must match "
            f"[a-zA-Z0-9][a-zA-Z0-9_.\\-]{{0,63}}"
        )
    return name


# ─── Tag/untag operations ───────────────────────────────────────────────────


def tag_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    project: str,
) -> bool:
    """Add a project tag to an atom's scope_tags. Idempotent.

    The scope_tags column stores JSON. We extend it with
    ``{"projects": ["name1", "name2", ...]}`` while preserving any
    existing keys other writers (palace, etc.) put there.

    Returns True if a tag was added, False if it was already present or
    the atom doesn't exist.
    """
    project = normalize_project_name(project)

    row = conn.execute(
        "SELECT scope_tags FROM atoms WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if row is None:
        return False

    existing_json = row[0] or "{}"
    try:
        tags: dict[str, Any] = json.loads(existing_json)
        if not isinstance(tags, dict):
            # If something stored a list there, migrate to dict shape.
            tags = {"_legacy": tags}
    except json.JSONDecodeError:
        tags = {}

    projects = tags.get("projects", [])
    if not isinstance(projects, list):
        projects = []
    if project in projects:
        return False  # already tagged

    projects.append(project)
    tags["projects"] = projects

    conn.execute(
        "UPDATE atoms SET scope_tags = ? WHERE atom_id = ?",
        (json.dumps(tags, sort_keys=True), atom_id),
    )
    conn.commit()
    return True


def untag_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    project: str,
) -> bool:
    """Remove a project tag. Returns True if removed, False if no-op."""
    project = normalize_project_name(project)

    row = conn.execute(
        "SELECT scope_tags FROM atoms WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if row is None or not row[0]:
        return False

    try:
        tags: dict[str, Any] = json.loads(row[0])
    except json.JSONDecodeError:
        return False
    if not isinstance(tags, dict):
        return False

    projects = tags.get("projects", [])
    if not isinstance(projects, list) or project not in projects:
        return False

    projects.remove(project)
    tags["projects"] = projects

    conn.execute(
        "UPDATE atoms SET scope_tags = ? WHERE atom_id = ?",
        (json.dumps(tags, sort_keys=True), atom_id),
    )
    conn.commit()
    return True


def projects_for_atom(
    conn: sqlite3.Connection, atom_id: str,
) -> list[str]:
    """Read project tags for an atom. Empty list if untagged or missing."""
    row = conn.execute(
        "SELECT scope_tags FROM atoms WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if row is None or not row[0]:
        return []
    try:
        tags = json.loads(row[0])
    except json.JSONDecodeError:
        return []
    if not isinstance(tags, dict):
        return []
    projects = tags.get("projects", [])
    return [p for p in projects if isinstance(p, str)]


# ─── Project-scoped retrieval wrapper ───────────────────────────────────────


@dataclass
class ScopedHit:
    """One hit with project-scope info."""
    atom_id: str
    summary: str
    score: float
    projects: list[str]
    in_target: bool


def search_in_project(
    conn: sqlite3.Connection,
    query: str,
    *,
    project: str,
    query_vec: list[float] | None = None,
    top_k: int = 10,
    include_global: bool = True,
) -> list[ScopedHit]:
    """Project-scoped hybrid search.

    Calls the existing ``hybrid_search`` and post-filters by project tag.
    With ``include_global=True`` (default), atoms with no project tag
    are also included — they're considered "shared knowledge."

    Returns ScopedHit list, sorted by relevance, with ``in_target=True``
    iff the atom is tagged with the queried project.
    """
    project = normalize_project_name(project)

    # Local import to keep this module independent of memory/retrieval
    # initialization order.
    from .memory.retrieval import hybrid_search

    # Ask for more raw hits than top_k since we'll filter.
    raw = hybrid_search(
        conn, query, query_vec=query_vec, top_k=max(top_k * 3, top_k),
    )

    out: list[ScopedHit] = []
    for hit in raw:
        projects = _extract_projects_from_metadata(hit.metadata)
        in_target = project in projects
        if not in_target and not (include_global and not projects):
            continue
        out.append(ScopedHit(
            atom_id=hit.atom_id,
            summary=hit.summary,
            score=getattr(hit, "fused_score", 0.0),
            projects=projects,
            in_target=in_target,
        ))
        if len(out) >= top_k:
            break
    return out


def _extract_projects_from_metadata(metadata: Any) -> list[str]:
    """Pull the projects list out of an atom's metadata blob."""
    if not metadata:
        return []
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return []
    if not isinstance(metadata, dict):
        return []
    projects = metadata.get("projects") or metadata.get("scope_tags", {}).get("projects")
    if isinstance(projects, list):
        return [p for p in projects if isinstance(p, str)]
    return []


# ─── Bulk tagging by trace ──────────────────────────────────────────────────


def tag_atoms_by_creator(
    conn: sqlite3.Connection,
    *,
    actor_pattern: str,
    project: str,
) -> int:
    """Tag all atoms whose ``created_by`` actor matches ``actor_pattern``.

    Useful for retroactive tagging: "tag every atom created by the
    dream-atomize step for dream-01J9... with project=genesis-seeds".

    Returns the number of atoms newly tagged. Existing tags are not
    duplicated.
    """
    project = normalize_project_name(project)
    rows = conn.execute(
        "SELECT atom_id FROM atoms WHERE created_by LIKE ?",
        (f"%{actor_pattern}%",),
    ).fetchall()
    n = 0
    for (atom_id,) in rows:
        if tag_atom(conn, atom_id, project):
            n += 1
    return n


__all__ = [
    "ScopedHit",
    "is_valid_project_name",
    "normalize_project_name",
    "projects_for_atom",
    "search_in_project",
    "tag_atom",
    "tag_atoms_by_creator",
    "untag_atom",
]
