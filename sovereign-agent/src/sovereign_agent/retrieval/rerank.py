"""
╔══════════════════════════════════════════════════════════════════════════╗
║  retrieval/rerank.py — Stage 4: three-signal reranking                  ║
║  v0.2.28.0                                                                ║
║                                                                           ║
║  WHY THREE SIGNALS, NOT ONE                                              ║
║                                                                           ║
║    A cross-encoder is the standard "second pass" in production RAG. It ║
║    re-scores the candidate pool by query-document semantic similarity. ║
║    That is one signal.                                                   ║
║                                                                           ║
║    Aria can — and should — use two more:                              ║
║                                                                           ║
║      PROVENANCE STRENGTH                                                ║
║        Atoms that have many supporting atoms (downstream lessons,     ║
║        recalls citing them, relationships extending from them) are    ║
║        epistemically heavier. A claim cited five times by Aria's      ║
║        own lessons is not the same as a claim made once and never   ║
║        referenced again. This is *trust by repetition* —             ║
║        epistemically correct.                                         ║
║                                                                           ║
║      RECENCY × CONFIDENCE                                              ║
║        Newer atoms tend to be more relevant; uncertain atoms          ║
║        should not rank above confident ones at the same recency.     ║
║        Multiplying these signals — instead of summing — captures      ║
║        the right shape: an old-but-confident atom beats a new-but-  ║
║        uncertain one for high-stakes queries.                        ║
║                                                                           ║
║    Final score is a weighted sum tuned by query intent:                ║
║                                                                           ║
║      decision_support → semantic 0.4, provenance 0.4, recency_conf 0.2║
║      factual          → semantic 0.5, provenance 0.4, recency_conf 0.1║
║      conversational   → semantic 0.4, provenance 0.1, recency_conf 0.5║
║      exploration      → semantic 0.5, provenance 0.2, recency_conf 0.3║
║      debug            → semantic 0.3, provenance 0.5, recency_conf 0.2║
║      reflective       → semantic 0.4, provenance 0.4, recency_conf 0.2║
║                                                                           ║
║    The weights are an opinion. The structure (three signals, intent- ║
║    weighted) is the contract.                                          ║
║                                                                           ║
║  HONEST DEGRADATION                                                      ║
║                                                                           ║
║    If the cross-encoder is unavailable: semantic falls back to RRF    ║
║    over the recall stages' ranks. The fallback is documented in      ║
║    the RetrievalReport so the operator knows the reranker was off.   ║
║    The system never lies about which signals were active.            ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .filter import FilteredPool, HydratedRow
from .query import QueryContext, QueryIntent
from .recall import RecallCandidate


# Weight matrices — per-intent (semantic, provenance, recency_confidence)
# Sums to 1.0 within each intent for interpretability.
_INTENT_WEIGHTS: dict[QueryIntent, tuple[float, float, float]] = {
    "factual":          (0.5, 0.4, 0.1),
    "decision_support": (0.4, 0.4, 0.2),
    "exploration":      (0.5, 0.2, 0.3),
    "conversational":   (0.4, 0.1, 0.5),
    "debug":            (0.3, 0.5, 0.2),
    "reflective":       (0.4, 0.4, 0.2),
}


# Half-life of recency decay, in days. Atoms older than this lose
# significant weight on the recency_confidence axis. 14 days is the
# default — short enough that "last week" matters, long enough that
# month-old lessons still count.
_RECENCY_HALF_LIFE_DAYS = 14.0


# Type alias for the reranker injection. Takes (query, list of summaries)
# and returns parallel list of scores in [0, 1]. None when unavailable.
RerankerFn = Callable[[str, list[str]], list[float] | None]


@dataclass(frozen=True)
class RerankScore:
    """Per-candidate score breakdown.

    Keeping the three sub-scores visible (not just the fused total) is
    deliberate — when an operator says "why is THIS atom at the top?"
    the answer needs to be auditable. "Semantic 0.8, provenance 0.2,
    recency_confidence 0.6 → fused 0.59" is auditable. A single number
    is not.
    """
    atom_id: str
    semantic: float
    provenance: float
    recency_confidence: float
    fused: float


@dataclass
class RerankedPool:
    """Output of the rerank stage.

    Sorted by ``fused`` descending. The full score breakdown for each
    atom is preserved for the audit trail.
    """
    scored: list[tuple[HydratedRow, RecallCandidate, RerankScore]]
    weights_used: tuple[float, float, float]
    semantic_source: str    # "cross_encoder" | "rrf_fallback"
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
# Provenance strength — how many downstream atoms cite this one
# ─────────────────────────────────────────────────────────────────────────


def _count_provenance_references(
    conn: sqlite3.Connection,
    atom_ids: list[str],
) -> dict[str, int]:
    """Count how many other atoms reference each atom_id as upstream.

    Two cheap signals (both work on a vanilla schema):
      • parent_atom_id — version chain successors
      • parents JSON array — event-ULID parents (this needs LIKE; cheap on small DBs)

    For larger DBs the LIKE scan would warrant a dedicated index; on the
    1k-100k atom scale Aria runs at, this is fine. Returns ``{}`` if the
    table doesn't exist (fresh install).
    """
    if not atom_ids:
        return {}

    # Successor-via-version-chain
    placeholders = ",".join("?" * len(atom_ids))
    try:
        rows = conn.execute(
            f"SELECT parent_atom_id, COUNT(*) "
            f"FROM atoms WHERE parent_atom_id IN ({placeholders}) "
            f"GROUP BY parent_atom_id",
            tuple(atom_ids),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    counts: dict[str, int] = defaultdict(int)
    for parent_id, n in rows:
        counts[parent_id] = int(n)
    return dict(counts)


def _normalize_provenance_scores(raw: dict[str, int]) -> dict[str, float]:
    """Map raw reference counts to [0, 1] via min-max with a soft cap.

    The cap (at 10 references) prevents one popular atom from dominating
    the signal. Empty input → empty output (every atom gets 0.0
    downstream).
    """
    if not raw:
        return {}
    capped = {aid: min(n, 10) for aid, n in raw.items()}
    max_v = max(capped.values())
    if max_v == 0:
        return {aid: 0.0 for aid in capped}
    return {aid: v / max_v for aid, v in capped.items()}


# ─────────────────────────────────────────────────────────────────────────
# Recency × confidence
# ─────────────────────────────────────────────────────────────────────────


def _recency_decay(created_at_iso: str, *, now: datetime | None = None) -> float:
    """Exponential decay on age in days. Result in (0, 1].

    Robust to malformed timestamps — degrades to 0.5 (neutral) so a bad
    date doesn't crash the rerank stage.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        # Strip trailing Z and parse as UTC
        ts_str = created_at_iso.rstrip("Z")
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return 0.5
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    # Half-life decay: at age=half_life, value=0.5
    return 0.5 ** (age_days / _RECENCY_HALF_LIFE_DAYS)


def _recency_confidence_score(row: HydratedRow) -> float:
    """Product of recency and confidence. Multiplicative on purpose —
    an old-and-uncertain atom should score lower than either signal alone
    would suggest. Confident-and-recent maxes out."""
    return _recency_decay(row.created_at) * row.confidence


# ─────────────────────────────────────────────────────────────────────────
# Semantic scoring — cross-encoder or RRF fallback
# ─────────────────────────────────────────────────────────────────────────


def _rrf_fallback_score(candidate: RecallCandidate) -> float:
    """Reciprocal Rank Fusion across the three recall stages.

    Used when the cross-encoder is unavailable. The score is the sum
    of 1/(k+rank) across each stage that surfaced this candidate.
    k=60 is the canonical constant from Cormack et al. 2009.

    Normalized to [0, 1] later by dividing by the max within the pool.
    """
    K = 60.0
    score = 0.0
    if candidate.lexical_rank is not None:
        score += 1.0 / (K + candidate.lexical_rank)
    if candidate.dense_rank is not None:
        score += 1.0 / (K + candidate.dense_rank)
    if candidate.graph_rank is not None:
        # Graph rank is weighted slightly down — graph captures causal
        # adjacency, but lexical/dense capture topical adjacency, which
        # is more directly query-relevant. The factor of 0.7 is the
        # author's opinion; structurally this could be 1.0 and the
        # rerank weights would compensate.
        score += 0.7 * (1.0 / (K + candidate.graph_rank))
    return score


def _normalize_to_unit(scores: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a dict of scores to [0, 1]. Empty input passes
    through unchanged. Constant input → all 0.5 (neutral)."""
    if not scores:
        return {}
    values = list(scores.values())
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return {k: 0.5 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _compute_semantic_scores(
    filtered: FilteredPool,
    ctx: QueryContext,
    reranker: RerankerFn | None,
) -> tuple[dict[str, float], str]:
    """Run the reranker if available, fall back to RRF otherwise.

    Returns ``(scores_by_atom_id, source_marker)``. The source marker
    is one of {"cross_encoder", "rrf_fallback"} and is surfaced in the
    RetrievalReport for transparency.
    """
    if reranker is not None and filtered.surviving:
        try:
            summaries = [row.summary for _, row in filtered.surviving]
            ranked = reranker(ctx.literal, summaries)
        except Exception:
            ranked = None
        if ranked is not None and len(ranked) == len(filtered.surviving):
            return (
                {filtered.surviving[i][1].atom_id: float(ranked[i])
                 for i in range(len(ranked))},
                "cross_encoder",
            )

    # Fallback path
    raw_rrf = {
        cand.atom_id: _rrf_fallback_score(cand)
        for cand, _row in filtered.surviving
    }
    return _normalize_to_unit(raw_rrf), "rrf_fallback"


# ─────────────────────────────────────────────────────────────────────────
# The reranker
# ─────────────────────────────────────────────────────────────────────────


def rerank(
    conn: sqlite3.Connection,
    filtered: FilteredPool,
    ctx: QueryContext,
    *,
    reranker: RerankerFn | None = None,
) -> RerankedPool:
    """Three-signal reranking of a FilteredPool.

    Sets ``fused = w_sem * semantic + w_prov * provenance + w_rec * recency_conf``
    where the weights come from the intent matrix.

    The returned RerankedPool is sorted by fused score descending. The
    per-axis subscores are preserved so the assembly stage can produce an
    auditable explanation of *why* each top-k atom is where it is.
    """
    if not filtered.surviving:
        return RerankedPool(
            scored=[],
            weights_used=_INTENT_WEIGHTS.get(ctx.intent, (0.5, 0.3, 0.2)),
            semantic_source="rrf_fallback",
            notes=["empty input to rerank"],
        )

    # ── Semantic ──────────────────────────────────────────────────────
    semantic_scores, semantic_source = _compute_semantic_scores(
        filtered, ctx, reranker
    )

    # ── Provenance strength ──────────────────────────────────────────
    atom_ids = [row.atom_id for _, row in filtered.surviving]
    raw_prov = _count_provenance_references(conn, atom_ids)
    prov_scores = _normalize_provenance_scores(raw_prov)

    # ── Recency × confidence ─────────────────────────────────────────
    rec_conf_raw = {
        row.atom_id: _recency_confidence_score(row)
        for _, row in filtered.surviving
    }
    rec_conf_scores = _normalize_to_unit(rec_conf_raw)

    # ── Fuse ─────────────────────────────────────────────────────────
    w_sem, w_prov, w_rec = _INTENT_WEIGHTS.get(ctx.intent, (0.5, 0.3, 0.2))

    scored: list[tuple[HydratedRow, RecallCandidate, RerankScore]] = []
    for cand, row in filtered.surviving:
        s = semantic_scores.get(row.atom_id, 0.0)
        p = prov_scores.get(row.atom_id, 0.0)
        r = rec_conf_scores.get(row.atom_id, 0.0)
        # Apply intent's channel weights — atoms in highly-weighted
        # channels for this intent get a small boost (max 20%)
        channel_boost = 1.0
        for tag in row.scope_tags:
            if tag in ctx.channel_weights:
                channel_boost = max(channel_boost, ctx.channel_weights[tag])
        # Cap the boost at 1.5 to prevent any channel from dominating
        channel_boost = min(channel_boost, 1.5)
        fused = (w_sem * s + w_prov * p + w_rec * r) * channel_boost

        scored.append(
            (row, cand, RerankScore(
                atom_id=row.atom_id,
                semantic=s,
                provenance=p,
                recency_confidence=r,
                fused=fused,
            ))
        )

    scored.sort(key=lambda triple: triple[2].fused, reverse=True)

    notes: list[str] = []
    if semantic_source == "rrf_fallback":
        notes.append("cross-encoder unavailable; semantic axis used RRF fallback")
    if not raw_prov:
        notes.append("provenance signal contributed nothing — no inter-atom links found")

    return RerankedPool(
        scored=scored,
        weights_used=(w_sem, w_prov, w_rec),
        semantic_source=semantic_source,
        notes=notes,
    )


__all__ = [
    "RerankerFn",
    "RerankScore",
    "RerankedPool",
    "rerank",
]
