"""Hybrid retrieval: vector ANN + FTS lexical, fused via Reciprocal Rank Fusion.

Architecture §8: the read side of the memory subsystem. RRF is the simple,
robust fusion method — it doesn't require score calibration between two
fundamentally incomparable metrics (cosine distance vs BM25), it just uses
ranks. Empirically beats hand-tuned weighted sums in most retrieval setups.

For each query:
  1. Vector search → top-N atoms by embedding cosine
  2. FTS5 search   → top-N atoms by BM25
  3. Fuse: score(a) = Σ_q 1 / (k + rank_q(a))     where k = 60 (standard)
  4. Return top-K with both ranks visible for debugging

When the agent is asked "find atoms about X", it should call ``hybrid_search``
with the query string. ``embed_query`` is called once internally; callers
who already have an embedding can pass it via ``query_vec``.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..config import SETTINGS
from ..ollama_client import OllamaClient

RRF_K = 60   # standard constant from Cormack et al. 2009
DEFAULT_TOP_N = 50
DEFAULT_TOP_K = 10


@dataclass
class RetrievalHit:
    """One result from hybrid search."""

    atom_id: str
    summary: str
    fused_score: float
    vec_rank: int | None    # 1-indexed; None if not in vec results
    fts_rank: int | None    # 1-indexed; None if not in fts results
    metadata: dict[str, Any]


def _serialize_vec(vec: list[float]) -> bytes:
    """sqlite-vec expects a packed float32 blob."""
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


def _atom_index_text(atom) -> str:
    """The text actually indexed — summary plus whatever inline content is
    available, so a lesson's failure_mode/correction detail is searchable,
    not just its one-line summary."""
    content = atom.content_ref.get("content", "") if atom.content_ref.get("kind") == "inline" else ""
    return f"{atom.summary}\n{content}".strip()


def index_atom_fts(conn: sqlite3.Connection, atom) -> None:
    """Sync, no external calls. NOTE: write_atom() (memory/atom.py) now
    does this automatically for every new write — this standalone
    function is for backfilling atoms written BEFORE that fix (found live
    2026-08-02: write_atom() had never populated fts_atoms/vec_atoms at
    all, so every atom written through the normal tool path before this
    session was permanently unsearchable). Do not call this after
    write_atom() for a fresh write — that would insert a duplicate row."""
    conn.execute(
        "INSERT INTO fts_atoms (atom_id, summary, content) VALUES (?, ?, ?)",
        (atom.atom_id, atom.summary, _atom_index_text(atom)),
    )


async def index_atom_vector(
    conn: sqlite3.Connection, atom, *, client: OllamaClient | None = None,
) -> None:
    """The embedding half — async (a real model call), so callers already
    inside an async Tool.execute() should await this after write_atom() +
    index_atom_fts(). Failure here is intentionally non-fatal to the
    caller's own atom write (an unembedded-but-FTS-indexed atom is still
    half-searchable and strictly better than the write silently dropping),
    but IS surfaced — see index_atom()'s return value."""
    client = client or OllamaClient()
    vec = await client.embed(model=SETTINGS.embed_model, prompt=_atom_index_text(atom))
    blob = _serialize_vec(vec)
    conn.execute(
        "INSERT INTO vec_atoms (atom_id, embedding) VALUES (?, ?)",
        (atom.atom_id, blob),
    )


def vec_search(
    conn: sqlite3.Connection, query_vec: list[float], top_n: int = DEFAULT_TOP_N
) -> list[tuple[str, float]]:
    """Top-N atom_ids by vector distance. Returns [(atom_id, distance), ...]."""
    blob = _serialize_vec(query_vec)
    rows = conn.execute(
        "SELECT atom_id, distance FROM vec_atoms "
        "WHERE embedding MATCH ? AND k = ? "
        "ORDER BY distance",
        (blob, top_n),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def fts_search(
    conn: sqlite3.Connection, query_text: str, top_n: int = DEFAULT_TOP_N
) -> list[tuple[str, float]]:
    """Top-N atom_ids by BM25 (FTS5). Returns [(atom_id, bm25), ...]."""
    # Escape FTS5 special chars conservatively — the model may pass anything
    safe = query_text.replace('"', '""')
    rows = conn.execute(
        "SELECT atom_id, bm25(fts_atoms) AS score "
        "FROM fts_atoms "
        'WHERE fts_atoms MATCH ? '
        "ORDER BY score "
        "LIMIT ?",
        (f'"{safe}"', top_n),
    ).fetchall()
    # bm25 is "lower is better" in fts5 — invert sign so higher is better
    return [(r[0], -r[1]) for r in rows]


def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = RRF_K
) -> dict[str, float]:
    """Standard RRF: score(d) = Σ 1/(k + rank(d)) across all rankings."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return dict(scores)


def hybrid_search(
    conn: sqlite3.Connection,
    query_text: str,
    *,
    query_vec: list[float] | None = None,
    top_n: int = DEFAULT_TOP_N,
    top_k: int = DEFAULT_TOP_K,
    client: OllamaClient | None = None,
) -> list[RetrievalHit]:
    """End-to-end hybrid retrieval. Embeds the query if no vec is supplied."""
    if query_vec is None:
        client = client or OllamaClient()
        # Sync wrapper around the async embed call — retrieval is called from
        # both sync (tools) and async (loop) contexts. We use the async client
        # via asyncio.run when no loop is active.
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            query_vec = asyncio.run(
                client.embed(model=SETTINGS.embed_model, prompt=query_text)
            )
        else:
            # We're already inside an event loop; caller must await us via thread
            raise RuntimeError(
                "hybrid_search called from within a running loop without query_vec; "
                "embed first then pass query_vec=..."
            )

    vec_hits = vec_search(conn, query_vec, top_n=top_n)
    fts_hits = fts_search(conn, query_text, top_n=top_n)

    vec_ranking = [aid for aid, _ in vec_hits]
    fts_ranking = [aid for aid, _ in fts_hits]
    vec_rank_lookup = {aid: i + 1 for i, aid in enumerate(vec_ranking)}
    fts_rank_lookup = {aid: i + 1 for i, aid in enumerate(fts_ranking)}

    fused = reciprocal_rank_fusion([vec_ranking, fts_ranking])
    if not fused:
        return []

    top_ids = sorted(fused, key=lambda a: fused[a], reverse=True)[:top_k]

    # Hydrate with summary + metadata in one query
    placeholders = ",".join("?" * len(top_ids))
    rows = conn.execute(
        f"SELECT atom_id, summary, type, confidence, scope_tags, version "
        f"FROM atoms WHERE atom_id IN ({placeholders}) "
        "AND superseded_at IS NULL",
        tuple(top_ids),
    ).fetchall()
    by_id = {r[0]: r for r in rows}

    out: list[RetrievalHit] = []
    for aid in top_ids:
        if aid not in by_id:
            continue   # superseded — skip
        _, summary, atype, conf, tags_json, version = by_id[aid]
        out.append(
            RetrievalHit(
                atom_id=aid,
                summary=summary,
                fused_score=fused[aid],
                vec_rank=vec_rank_lookup.get(aid),
                fts_rank=fts_rank_lookup.get(aid),
                metadata={
                    "type": atype,
                    "confidence": conf,
                    "scope_tags": json.loads(tags_json) if tags_json else [],
                    "version": version,
                },
            )
        )
    return out
