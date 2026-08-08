"""
╔══════════════════════════════════════════════════════════════════════════╗
║  retrieval/recall.py — Stage 2: multi-source recall                     ║
║  v0.2.28.0                                                                ║
║                                                                           ║
║  THREE PARALLEL RETRIEVERS                                               ║
║                                                                           ║
║    Naive RAG runs one retriever (usually dense embeddings). Even        ║
║    hybrid RAG runs two (lexical + dense). This module runs THREE —    ║
║    adding a graph-recall pass that uses Aria's provenance edges.      ║
║                                                                           ║
║    Each retriever has a different failure mode:                        ║
║                                                                           ║
║      LEXICAL (BM25)       — fails on paraphrase, synonyms             ║
║      DENSE (embeddings)   — fails on rare names, code, exact phrases  ║
║      GRAPH (provenance)   — fails when focus is empty or unrelated    ║
║                                                                           ║
║    The three are complementary. An atom that doesn't surface in any   ║
║    of the three almost certainly is not relevant.                     ║
║                                                                           ║
║  THE GRAPH PASS — what makes this different                              ║
║                                                                           ║
║    Standard RAG has no awareness of *why* an atom exists. The         ║
║    provenance graph encodes that: "atom A was written because event   ║
║    E happened, which referenced atom B." Walking backward from the    ║
║    operator's current focus surfaces atoms that are *causally        ║
║    relevant*, not just textually similar.                             ║
║                                                                           ║
║    Concrete example: operator is working on a deployment script      ║
║    (focus="deploy hotfix to prod"). Lexical retrieval finds atoms    ║
║    with the word "deploy." Dense retrieval finds atoms semantically  ║
║    near deployment. Graph retrieval, starting from the most-recent   ║
║    "deploy" atoms in the operator's history, walks backward and       ║
║    surfaces the lesson Aria learned three months ago about the       ║
║    rollback step that always gets missed — which has no textual or  ║
║    semantic overlap with the current query but is causally linked.   ║
║                                                                           ║
║  HONEST DEGRADATION                                                      ║
║                                                                           ║
║    If the embedding model is unavailable: dense skipped, marker       ║
║      returned so downstream knows.                                    ║
║    If FTS5 returns no results: lexical contributes nothing, no error.║
║    If focus is empty: graph pass skipped.                             ║
║    All three failing simultaneously: returns empty pool with the     ║
║      gap report explaining which retrievers were active.              ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
import sqlite3
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .query import QueryContext


# ─────────────────────────────────────────────────────────────────────────
# Candidate types
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecallCandidate:
    """One atom that one or more retrievers surfaced.

    The candidate carries ranks from EACH retriever that surfaced it —
    not just one fused score. Downstream stages need per-retriever ranks
    to detect "this was in lexical top-5 but nowhere in dense" patterns,
    which signal a rare-but-relevant term match worth keeping even when
    fused rank is low.
    """
    atom_id: str
    lexical_rank: int | None = None     # 1-indexed; None if not surfaced
    dense_rank: int | None = None
    graph_rank: int | None = None
    graph_distance: int | None = None   # hops from a focus anchor (graph only)


@dataclass
class RecallPool:
    """The output of the recall stage.

    ``candidates`` is the deduplicated set across all three retrievers,
    with per-retriever ranks preserved.

    ``active_retrievers`` is which of the three actually contributed
    (ran AND returned at least one hit). Downstream uses this to weight
    fusion.

    ``attempted_retrievers`` is which of the three actually tried (ran,
    regardless of outcome). The difference between attempted and active
    is the set of retrievers that ran-but-returned-empty. The difference
    between {lexical, dense, graph} and attempted is the set that didn't
    even try (e.g. dense without an embedder). The gap report needs
    both distinctions to give the operator an honest answer.

    ``retriever_pool_sizes`` is for observability: did one retriever
    dominate? Did one return nothing? Keys are only present for
    retrievers that attempted.
    """
    candidates: list[RecallCandidate]
    active_retrievers: frozenset[str] = field(default_factory=frozenset)
    attempted_retrievers: frozenset[str] = field(default_factory=frozenset)
    retriever_pool_sizes: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
# Lexical recall — BM25 via FTS5 (uses existing fts_atoms table)
# ─────────────────────────────────────────────────────────────────────────


def _fts_escape(query_text: str) -> str:
    """Build an FTS5 MATCH expression for natural-language queries.

    The model and operators pass conversational queries like "should I ship
    the rollback to production now?" — a strict phrase match would require
    that exact sentence to appear in an indexed atom (it never does). The
    right semantics for natural language is: match any atom containing any
    significant token from the query.

    Strategy:
      1. Tokenize on whitespace and punctuation
      2. Lowercase, drop stopwords and tokens < 3 chars
      3. Each surviving token gets quoted to escape FTS5 special chars
         (so operator words like "AND" / "NOT" / "OR" inside the query
         become literal tokens, not FTS5 operators)
      4. Join with " OR " — any token matching is a hit

    Falls back to a single quoted phrase if no significant tokens survive
    the filter (preserves the old behavior for unusual inputs like single
    short tokens, queries entirely in another script, etc).
    """
    # Tokenize: anything that's not alphanumeric/underscore/hyphen separates
    raw_tokens = re.findall(r"[A-Za-z0-9_\-]+", query_text)
    significant: list[str] = []
    for tok in raw_tokens:
        tok_low = tok.lower()
        if len(tok_low) < 3:
            continue
        if tok_low in _FTS_STOPWORDS:
            continue
        # Escape inner quotes by doubling, then wrap each token in quotes
        # so it's treated as a literal token by FTS5 (no operator interpretation)
        safe = tok_low.replace('"', '""')
        significant.append(f'"{safe}"')

    if not significant:
        # Degenerate input — fall back to a quoted phrase of the original.
        # This is the old behavior; preserved for edge cases.
        safe = query_text.replace('"', '""')
        return f'"{safe}"'

    # OR-join all significant tokens. FTS5 supports OR as an operator
    # outside of quoted strings; inside quotes, tokens are literal.
    return " OR ".join(significant)


# Standard English stopwords. Filtering these from FTS queries dramatically
# cuts false-positive matches without losing meaning — "the deploy" and
# "deploy" should return the same atoms. List is short on purpose; adding
# domain terms here would couple FTS behavior to a specific vocabulary.
_FTS_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "from", "into", "onto", "with", "without",
    "that", "this", "these", "those", "are", "was", "were", "been",
    "being", "have", "has", "had", "having", "you", "your", "yours",
    "should", "would", "could", "will", "shall", "may", "might", "must",
    "what", "when", "where", "which", "who", "whom", "why", "how",
    "about", "above", "below", "after", "before",
    "but", "not", "now", "then", "than",
})


def lexical_recall(
    conn: sqlite3.Connection,
    ctx: QueryContext,
    *,
    top_n: int = 40,
) -> list[tuple[str, float]]:
    """Top-N atoms by BM25.

    Returns [(atom_id, score)] sorted by score descending. Score is the
    NEGATED BM25 — FTS5 returns lower-is-better, we invert so consumers
    can sort uniformly.

    Empty result list when:
      - fts_atoms table doesn't exist (very fresh install)
      - query has no tokens that match anything
      - the safe-quote produced something unparseable
    """
    safe = _fts_escape(ctx.normalized)
    try:
        rows = conn.execute(
            "SELECT atom_id, bm25(fts_atoms) AS score "
            "FROM fts_atoms "
            "WHERE fts_atoms MATCH ? "
            "ORDER BY score "
            "LIMIT ?",
            (safe, top_n),
        ).fetchall()
    except sqlite3.OperationalError:
        # Table missing, malformed query — both legitimate degradation paths
        return []
    return [(r[0], -float(r[1])) for r in rows]


# ─────────────────────────────────────────────────────────────────────────
# Dense recall — vec_atoms via sqlite-vec (uses existing virtual table)
# ─────────────────────────────────────────────────────────────────────────


def _serialize_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


# Type alias for the embedder injection. The function takes a string and
# returns a list of floats. This is what callers must provide — usually
# a wrapper around OllamaClient.embed.
EmbedderFn = Callable[[str], list[float] | None]


def dense_recall(
    conn: sqlite3.Connection,
    ctx: QueryContext,
    *,
    embedder: EmbedderFn,
    top_n: int = 40,
) -> tuple[list[tuple[str, float]], bool]:
    """Top-N atoms by vector distance.

    Returns ``(hits, embedder_ok)``. If the embedder returns None or
    raises, the dense stage is skipped and we return (empty, False) —
    downstream uses the False to mark dense as inactive in the report.

    Score returned is the *negation* of distance (higher = better),
    matching lexical's convention.
    """
    try:
        vec = embedder(ctx.literal)
    except Exception:
        vec = None

    if vec is None or not vec:
        return [], False

    blob = _serialize_vec(vec)
    try:
        rows = conn.execute(
            "SELECT atom_id, distance FROM vec_atoms "
            "WHERE embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (blob, top_n),
        ).fetchall()
    except sqlite3.OperationalError:
        return [], False

    return [(r[0], -float(r[1])) for r in rows], True


# ─────────────────────────────────────────────────────────────────────────
# Graph recall — the novel stage, using provenance walk from focus anchors
# ─────────────────────────────────────────────────────────────────────────


def _find_anchor_atoms(
    conn: sqlite3.Connection,
    anchor_terms: tuple[str, ...],
    *,
    max_anchors: int = 5,
) -> list[str]:
    """Find atom_ids that match any of the focus-anchor terms via FTS.

    Returns at most ``max_anchors`` atom_ids — these become seed nodes
    for the provenance walk. The graph pass doesn't need many seeds;
    its job is to bring in causally-linked atoms that the other passes
    missed, not to be its own bulk retriever.

    Empty list if anchor_terms is empty OR no atoms match. Either way,
    the graph pass becomes a no-op.
    """
    if not anchor_terms:
        return []

    # OR-join the terms into one FTS query. We deliberately use the
    # OR-form here (the existing fts_search uses phrase-AND) because
    # focus-anchor terms are independent signals — any one matching
    # is a signal.
    or_query = " OR ".join(f'"{t}"' for t in anchor_terms[:5])
    try:
        rows = conn.execute(
            "SELECT atom_id FROM fts_atoms WHERE fts_atoms MATCH ? "
            "ORDER BY bm25(fts_atoms) LIMIT ?",
            (or_query, max_anchors),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def graph_recall(
    conn: sqlite3.Connection,
    ctx: QueryContext,
    *,
    max_depth: int = 3,
    max_nodes: int = 30,
) -> list[tuple[str, int]]:
    """Walk the provenance graph backward from focus-anchor atoms.

    Returns [(atom_id, hops_from_anchor)] sorted by hop count ascending.
    Closer atoms come first — they are causally nearer the operator's
    current focus.

    Empty list when:
      - focus is empty (no anchor terms)
      - no atoms match the anchor terms
      - provenance module not importable in this context
    """
    if not ctx.focus_anchor_terms:
        return []

    anchor_ids = _find_anchor_atoms(conn, ctx.focus_anchor_terms)
    if not anchor_ids:
        return []

    try:
        from ..provenance import walk_backward
    except ImportError:
        return []

    # Walk each anchor; merge by min-distance
    distance: dict[str, int] = {}
    for anchor in anchor_ids:
        try:
            graph = walk_backward(conn, anchor, max_depth=max_depth,
                                  max_nodes=max_nodes)
        except Exception:
            continue
        # BFS over the graph rooted at anchor; track hop distance
        # The ProvenanceGraph's edges are source→target where source is upstream
        # (because the walk is "what informed me"). We want distance from anchor
        # outward, so we treat the graph as having edges from the anchor down
        # to its upstream nodes.
        adjacency: dict[str, list[str]] = defaultdict(list)
        for e in graph.edges:
            adjacency[e.target].append(e.source)
        # BFS
        frontier = [(anchor, 0)]
        visited = {anchor}
        while frontier:
            node, d = frontier.pop(0)
            if node not in distance or d < distance[node]:
                distance[node] = d
            if d >= max_depth:
                continue
            for nxt in adjacency.get(node, []):
                if nxt not in visited:
                    visited.add(nxt)
                    frontier.append((nxt, d + 1))

    # Exclude the anchor atoms themselves from the "graph contribution"
    # — they would have been found by lexical/dense too. The novelty
    # of graph recall is the indirect neighbors.
    anchor_set = set(anchor_ids)
    out = [(aid, d) for aid, d in distance.items() if aid not in anchor_set]
    out.sort(key=lambda x: x[1])  # closer first
    return out


# ─────────────────────────────────────────────────────────────────────────
# Fusion — all three sources into one RecallPool
# ─────────────────────────────────────────────────────────────────────────


def recall(
    conn: sqlite3.Connection,
    ctx: QueryContext,
    *,
    embedder: EmbedderFn | None = None,
    top_n_per_source: int = 40,
    graph_max_nodes: int = 30,
) -> RecallPool:
    """Run all three retrievers, merge into a single candidate pool.

    The merge is rank-preserving: each candidate carries the rank it
    achieved in each retriever that surfaced it. No score fusion happens
    here — that's the reranker's job. This stage's contract is "give us
    everything that could plausibly be relevant, with provenance about
    which retriever found it."

    ``embedder`` is optional; if absent or returns None, dense recall is
    skipped. The pool will still have lexical and graph results. The
    ``active_retrievers`` set in the output marks which stages actually
    ran.
    """
    active: set[str] = set()         # ran AND returned >0 hits
    attempted: set[str] = set()      # ran (regardless of outcome)
    notes: list[str] = []
    pool_sizes: dict[str, int] = {}  # only set for retrievers that actually ran

    # ── Lexical ──────────────────────────────────────────────────────
    # Lexical always attempts — the FTS5 table either exists or doesn't,
    # and lexical_recall returns [] in the latter case (silently).
    attempted.add("lexical")
    lexical_hits = lexical_recall(conn, ctx, top_n=top_n_per_source)
    pool_sizes["lexical"] = len(lexical_hits)
    if lexical_hits:
        active.add("lexical")
    else:
        notes.append("lexical returned 0 hits — query may have no significant tokens matching any atom")
    lexical_rank = {aid: i + 1 for i, (aid, _) in enumerate(lexical_hits)}

    # ── Dense ────────────────────────────────────────────────────────
    if embedder is None:
        # Did not attempt — caller didn't provide an embedder
        notes.append("dense skipped — no embedder provided")
        dense_hits: list[tuple[str, float]] = []
        dense_rank: dict[str, int] = {}
    else:
        attempted.add("dense")
        dense_hits, ok = dense_recall(
            conn, ctx, embedder=embedder, top_n=top_n_per_source
        )
        pool_sizes["dense"] = len(dense_hits)
        if ok and dense_hits:
            active.add("dense")
        elif ok and not dense_hits:
            notes.append("dense returned 0 hits — vector index may be empty")
        else:
            notes.append("dense unavailable — embedder failed or vec_atoms missing")
        dense_rank = {aid: i + 1 for i, (aid, _) in enumerate(dense_hits)}

    # ── Graph ────────────────────────────────────────────────────────
    if not ctx.focus_anchor_terms:
        # Did not attempt — no focus to anchor on
        graph_hits: list[tuple[str, int]] = []
        notes.append("graph skipped — no focus_anchor_terms")
    else:
        attempted.add("graph")
        graph_hits = graph_recall(conn, ctx, max_nodes=graph_max_nodes)
        pool_sizes["graph"] = len(graph_hits)
        if graph_hits:
            active.add("graph")
        else:
            notes.append("graph returned 0 hits — focus anchors yielded no neighbors")
    graph_rank = {aid: i + 1 for i, (aid, _) in enumerate(graph_hits)}
    graph_distance = {aid: d for aid, d in graph_hits}

    # ── Fuse: deduplicate, preserve per-retriever ranks ──────────────
    all_ids: set[str] = (
        set(lexical_rank.keys())
        | set(dense_rank.keys())
        | set(graph_rank.keys())
    )

    candidates = [
        RecallCandidate(
            atom_id=aid,
            lexical_rank=lexical_rank.get(aid),
            dense_rank=dense_rank.get(aid),
            graph_rank=graph_rank.get(aid),
            graph_distance=graph_distance.get(aid),
        )
        for aid in all_ids
    ]

    return RecallPool(
        candidates=candidates,
        active_retrievers=frozenset(active),
        attempted_retrievers=frozenset(attempted),
        retriever_pool_sizes=pool_sizes,
        notes=notes,
    )


__all__ = [
    "RecallCandidate",
    "RecallPool",
    "EmbedderFn",
    "lexical_recall",
    "dense_recall",
    "graph_recall",
    "recall",
]
