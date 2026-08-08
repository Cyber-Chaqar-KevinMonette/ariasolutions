"""
╔══════════════════════════════════════════════════════════════════════════╗
║  retrieval — the Sovereign Retrieval Pipeline                            ║
║  v0.2.28.0                                                                ║
║                                                                           ║
║  Six stages between an operator's question and a witnessed answer:      ║
║                                                                           ║
║      1. understand_query (query.py)                                      ║
║           parse + classify + contextualize via AriaState                ║
║                                                                           ║
║      2. recall (recall.py)                                               ║
║           three parallel retrievers: lexical, dense, graph              ║
║                                                                           ║
║      3. constitutional_filter (filter.py)                                ║
║           untrusted-input + confidence floor + privacy + bitemporal    ║
║                                                                           ║
║      4. rerank (rerank.py)                                               ║
║           three signals: semantic + provenance + recency_confidence    ║
║                                                                           ║
║      5. assemble (assembly.py)                                           ║
║           witnessed hits + confidence ceiling + gap report + hints     ║
║                                                                           ║
║      6. (caller acts on hints or stops)                                  ║
║                                                                           ║
║  USAGE                                                                   ║
║                                                                           ║
║      from sovereign_agent.retrieval import retrieve                     ║
║      report = retrieve(query="...", conn=atoms_conn)                    ║
║      for hit in report.hits:                                            ║
║          ... use hit.summary, hit.confidence, hit.score ...             ║
║      if report.expansion_hints:                                         ║
║          ... decide whether to call again with the hint ...             ║
║                                                                           ║
║  CONTRAST WITH memory/retrieval.py                                       ║
║                                                                           ║
║    ``memory.retrieval.hybrid_search`` is the SUBSTRATE — a tight       ║
║    BM25 + dense + RRF fusion that returns ranked atom_ids.            ║
║                                                                           ║
║    This module is the ORCHESTRATOR — it calls into the substrate plus ║
║    the provenance graph, the constitutional layer, the bitemporal    ║
║    helpers, and the AriaState to produce a witnessed report.          ║
║                                                                           ║
║    Both coexist. Callers who need fast atom lookup keep using        ║
║    hybrid_search. Callers who need full witnessing use this.         ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sqlite3
from typing import Callable

from .assembly import (
    ExpansionAction,
    ExpansionHint,
    GapReport,
    RetrievalReport,
    WitnessedHit,
    assemble,
)
from .filter import FilteredPool, HydratedRow, constitutional_filter
from .query import (
    BitemporalFrame,
    QueryContext,
    QueryIntent,
    StakesLevel,
    now_iso,
    understand_query,
    understand_query_with_aria_state,
)
from .recall import (
    EmbedderFn,
    RecallCandidate,
    RecallPool,
    dense_recall,
    graph_recall,
    lexical_recall,
    recall,
)
from .rerank import (
    RerankScore,
    RerankedPool,
    RerankerFn,
    rerank,
)


def retrieve(
    *,
    query: str,
    conn: sqlite3.Connection,
    aria_focus: str = "",
    active_goals: int = 0,
    open_intentions: int = 0,
    intent_override: QueryIntent | None = None,
    stakes_override: StakesLevel | None = None,
    valid_at: str | None = None,
    as_known_at: str | None = None,
    embedder: EmbedderFn | None = None,
    reranker: RerankerFn | None = None,
    top_k: int = 5,
    top_n_per_source: int = 40,
) -> RetrievalReport:
    """Run the full Sovereign Retrieval Pipeline.

    Five stages run in order: understand_query → recall → filter →
    rerank → assemble. Every stage degrades honestly when its inputs
    are missing; the final RetrievalReport documents what ran, what
    fell back, and what was filtered.

    Parameters that matter:

      query           — the operator's question, in their own words
      conn            — atoms.db connection (open + ready)
      aria_focus      — current_focus from AriaState (drives graph recall)
      intent_override — bypass auto-detection if caller already knows
      stakes_override — bypass auto-detection (e.g. "I'm going to ship
                        based on this; treat as high")
      valid_at        — bitemporal: about what world-time?
      as_known_at     — bitemporal: as Aria knew when?
      embedder        — callable to embed query for dense recall; None disables
      reranker        — cross-encoder fn; None falls back to RRF
      top_k           — how many hits to return (default 5)
      top_n_per_source — recall pool size per retriever (default 40)

    Returns ``RetrievalReport`` — never raises for the empty-result case;
    instead returns a report with empty hits, a populated gap_report,
    and (likely) expansion_hints pointing at what could surface more.
    """
    ctx = understand_query(
        query=query,
        aria_focus=aria_focus,
        active_goals=active_goals,
        open_intentions=open_intentions,
        intent_override=intent_override,
        stakes_override=stakes_override,
        valid_at=valid_at,
        as_known_at=as_known_at,
    )

    pool = recall(
        conn, ctx, embedder=embedder, top_n_per_source=top_n_per_source
    )

    filtered = constitutional_filter(conn, pool, ctx)

    reranked = rerank(conn, filtered, ctx, reranker=reranker)

    return assemble(conn, ctx, pool, filtered, reranked, top_k=top_k)


def retrieve_from_state(
    *,
    query: str,
    conn: sqlite3.Connection,
    **kwargs,
) -> RetrievalReport:
    """Convenience: load AriaState from the connection, then call retrieve.

    Use this from CLI tools and the cockpit. Inside the agent loop,
    prefer the explicit ``retrieve`` so the loop's state cache is used.
    """
    from ..aria import load_state

    state = load_state(conn)
    return retrieve(
        query=query,
        conn=conn,
        aria_focus=state.current_focus,
        active_goals=state.active_goals,
        open_intentions=state.open_intentions,
        **kwargs,
    )


__all__ = [
    # Top-level orchestration
    "retrieve",
    "retrieve_from_state",
    # Query stage
    "QueryContext",
    "QueryIntent",
    "StakesLevel",
    "BitemporalFrame",
    "understand_query",
    "understand_query_with_aria_state",
    "now_iso",
    # Recall stage
    "RecallCandidate",
    "RecallPool",
    "EmbedderFn",
    "lexical_recall",
    "dense_recall",
    "graph_recall",
    "recall",
    # Filter stage
    "HydratedRow",
    "FilteredPool",
    "constitutional_filter",
    # Rerank stage
    "RerankScore",
    "RerankedPool",
    "RerankerFn",
    "rerank",
    # Assembly outputs
    "WitnessedHit",
    "GapReport",
    "ExpansionAction",
    "ExpansionHint",
    "RetrievalReport",
    "assemble",
]
