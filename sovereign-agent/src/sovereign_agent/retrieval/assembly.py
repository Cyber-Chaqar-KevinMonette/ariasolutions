"""
╔══════════════════════════════════════════════════════════════════════════╗
║  retrieval/assembly.py — Stage 5: witnessed-evidence assembly           ║
║  v0.2.28.0                                                                ║
║                                                                           ║
║  WHAT MAKES THE OUTPUT NOT-JUST-A-LIST-OF-DOCUMENTS                      ║
║                                                                           ║
║    Five things downstream needs that standard RAG does not provide:    ║
║                                                                           ║
║    1. THE WITNESS                                                       ║
║       Each hit carries its full epistemic context:                     ║
║         • content (summary, optionally full content_ref)              ║
║         • provenance breadcrumb (compact upstream chain)              ║
║         • created_at and created_by                                   ║
║         • confidence + whether source is operator-verified            ║
║         • score breakdown (semantic, provenance, recency_conf)        ║
║                                                                           ║
║    2. THE CONFIDENCE CEILING                                            ║
║       The MIN confidence across the top-k is reported as a ceiling.   ║
║       Downstream reasoning that depends on this evidence should not   ║
║       claim greater certainty than the weakest link supports.         ║
║       This is calibrated_uncertainty operationalized.                 ║
║                                                                           ║
║    3. THE GAP REPORT                                                    ║
║       What did we ask about that nothing answered?                    ║
║       Which channels were searched but came back empty?               ║
║       How many candidates were dropped by which constitutional        ║
║       filter? Standard RAG silently returns "best k I found"; this   ║
║       surfaces what's missing alongside what's present.               ║
║                                                                           ║
║    4. THE EXPANSION HINT                                                ║
║       When the report's confidence ceiling is low or gaps are large,  ║
║       the caller gets a concrete next-call suggestion:                ║
║         • "raise stakes=medium to see filtered atoms"                 ║
║         • "search channel=lessons explicitly — recall didn't surface  ║
║            any"                                                        ║
║         • "walk provenance from atom_id=X (this top hit has rich     ║
║            upstream not in the result set)"                           ║
║       This is "always enough context or a way to pull it from where  ║
║       it is" made operational. The retrieval system tells the caller ║
║       *how to go deeper*, not just what it found.                     ║
║                                                                           ║
║    5. THE RETRIEVAL TRACE                                               ║
║       Every stage's notes accumulated: which retrievers were active, ║
║       which signals fell back, what was dropped where. Observability ║
║       end-to-end. Auditable by humans.                                ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from .filter import FilteredPool, HydratedRow
from .query import QueryContext
from .recall import RecallCandidate, RecallPool
from .rerank import RerankedPool, RerankScore


# ─────────────────────────────────────────────────────────────────────────
# The witnessed hit
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WitnessedHit:
    """One top-k atom, fully witnessed.

    Every field has a reason:

      atom_id          — the canonical reference; cite this in downstream prose
      summary          — the ≤1000-char human-readable summary from the atom
      atom_type        — the typed kind (decision, doc, snippet, …)
      created_at       — when Aria first wrote this down
      created_by_actor — "operator" | "llm" | "system" — the trust marker
      confidence       — the atom's own self-assessed confidence
      score            — the rerank breakdown (auditable why-this-rank)
      provenance_breadcrumb — short chain of upstream atom_ids (max 5)
      surfaced_by      — which retrievers found this: subset of {lexical, dense, graph}

    The hit is frozen — once produced it does not get rewritten downstream.
    """
    atom_id: str
    summary: str
    atom_type: str
    created_at: str
    created_by_actor: str
    confidence: float
    score: RerankScore
    provenance_breadcrumb: tuple[str, ...]
    surfaced_by: frozenset[str]


# ─────────────────────────────────────────────────────────────────────────
# The gap report — what's missing
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GapReport:
    """Structured statement of what was NOT found / NOT shown.

    A gap report is the difference between "here are 3 results" (which
    is what RAG normally returns) and "here are 3 results, and you
    should know that 7 other candidates were filtered, two retrievers
    returned nothing, and these channels had no hits at all." The
    operator can act on the second answer; the first can mislead.
    """
    # Retrievers that ran but returned nothing
    empty_retrievers: tuple[str, ...]
    # Retrievers that were skipped entirely (no embedder, no focus, etc.)
    inactive_retrievers: tuple[str, ...]
    # Drops per constitutional reason
    constitutional_drops: dict[str, int]
    # How many candidates the recall stage surfaced before filtering
    raw_candidate_count: int
    # How many survived the filter
    filtered_count: int
    # How many were finally returned to the caller (top_k)
    returned_count: int


# ─────────────────────────────────────────────────────────────────────────
# Expansion hints — the "go deeper" pointers
# ─────────────────────────────────────────────────────────────────────────


ExpansionAction = Literal[
    "lower_stakes",            # call again with stakes=medium/low
    "search_specific_channel", # call again restricted to a named channel
    "walk_provenance_of",      # call walk_backward(atom_id) for a top hit
    "broaden_bitemporal",      # remove a tight valid_at constraint
    "allow_pending",           # set allow_pending=True
]


@dataclass(frozen=True)
class ExpansionHint:
    """One concrete suggestion for the caller's next retrieval call.

    Hints are *advisory* — they tell the caller what action might surface
    more relevant context. They never auto-execute. The caller (typically
    the agent loop or a planner) decides whether to take the hint or stop
    here.

    ``arg`` carries the parameter the action needs:
      lower_stakes              → new stakes level as string
      search_specific_channel   → channel name
      walk_provenance_of        → atom_id
      broaden_bitemporal        → "remove valid_at" or "remove as_known_at"
      allow_pending             → no arg (None)
    """
    action: ExpansionAction
    arg: str | None
    rationale: str


# ─────────────────────────────────────────────────────────────────────────
# The full report
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class RetrievalReport:
    """The final output of the pipeline.

    ``hits`` are the top-k witnessed atoms, ranked by fused score.
    ``confidence_ceiling`` is the MIN confidence across hits — downstream
        reasoning should not exceed this.
    ``gap_report`` documents what's missing.
    ``expansion_hints`` are 0..N concrete next-call suggestions.
    ``trace`` is every stage's notes for end-to-end observability.
    ``context`` is the QueryContext that produced this report — preserved
        for audit / debugging.
    """
    hits: list[WitnessedHit]
    confidence_ceiling: float
    gap_report: GapReport
    expansion_hints: list[ExpansionHint] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    context: QueryContext | None = None
    semantic_source: str = "rrf_fallback"

    @property
    def is_empty(self) -> bool:
        return not self.hits

    def render(self) -> str:
        """Render a compact human-readable report. Useful for `sov retrieve`
        CLI output and for inclusion in model prompts when full structure
        isn't needed."""
        lines = []
        if not self.hits:
            lines.append(f"no hits (confidence ceiling: {self.confidence_ceiling:.2f})")
        else:
            lines.append(
                f"{len(self.hits)} hits — confidence ceiling {self.confidence_ceiling:.2f}"
                f" — semantic via {self.semantic_source}"
            )
            for i, h in enumerate(self.hits, 1):
                lines.append(
                    f"  {i}. [{h.atom_id[:8]}] ({h.atom_type}, conf={h.confidence:.2f}, "
                    f"by={h.created_by_actor}) {h.summary[:120]}"
                )
                if h.provenance_breadcrumb:
                    chain = " ← ".join(a[:8] for a in h.provenance_breadcrumb)
                    lines.append(f"       provenance: {chain}")

        gr = self.gap_report
        if gr.constitutional_drops:
            nonzero = {k: v for k, v in gr.constitutional_drops.items() if v}
            if nonzero:
                lines.append(f"  dropped: {nonzero}")
        if gr.empty_retrievers or gr.inactive_retrievers:
            if gr.empty_retrievers:
                lines.append(f"  empty: {', '.join(gr.empty_retrievers)}")
            if gr.inactive_retrievers:
                lines.append(f"  inactive: {', '.join(gr.inactive_retrievers)}")
        if self.expansion_hints:
            lines.append(f"  hints: {len(self.expansion_hints)}")
            for h in self.expansion_hints:
                lines.append(f"    → {h.action}({h.arg}) — {h.rationale}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# Breadcrumb construction — compact upstream chain
# ─────────────────────────────────────────────────────────────────────────


def _build_breadcrumb(
    conn: sqlite3.Connection,
    atom_id: str,
    *,
    max_steps: int = 5,
) -> tuple[str, ...]:
    """Trace upstream via parent_atom_id for up to ``max_steps`` hops.

    Returns an ordered tuple [parent, grandparent, ...]. Stops at the
    first NULL parent (chain root) or after max_steps. Returns empty
    tuple on any error — provenance is best-effort, not load-bearing.
    """
    chain: list[str] = []
    current = atom_id
    seen = {current}
    try:
        for _ in range(max_steps):
            row = conn.execute(
                "SELECT parent_atom_id FROM atoms WHERE atom_id = ?",
                (current,),
            ).fetchone()
            if not row or row[0] is None:
                break
            parent = row[0]
            if parent in seen:
                # Defensive: should not happen, the chain is supposed to be
                # acyclic. Still — better to short-circuit than to loop.
                break
            chain.append(parent)
            seen.add(parent)
            current = parent
    except sqlite3.OperationalError:
        return ()
    return tuple(chain)


# ─────────────────────────────────────────────────────────────────────────
# Gap-report and expansion-hint generators
# ─────────────────────────────────────────────────────────────────────────


def _build_gap_report(
    recall_pool: RecallPool,
    filtered: FilteredPool,
    returned_count: int,
) -> GapReport:
    """Compute the gap report from prior-stage outputs.

    The distinction between empty and inactive is structural:
      • empty    = attempted but got 0 hits (lexical with no tokens matching)
      • inactive = did not attempt at all (dense with no embedder)

    Both surface to the operator differently. Empty says "your query
    didn't match anything in this index." Inactive says "this signal is
    offline; you could turn it on for better coverage."
    """
    expected_retrievers = {"lexical", "dense", "graph"}
    active = set(recall_pool.active_retrievers)
    attempted = set(recall_pool.attempted_retrievers)

    # Empty: in attempted but not in active — ran, got nothing
    empty = sorted(attempted - active)
    # Inactive: not even attempted
    fully_inactive = sorted(expected_retrievers - attempted)

    return GapReport(
        empty_retrievers=tuple(empty),
        inactive_retrievers=tuple(fully_inactive),
        constitutional_drops={
            k: v for k, v in filtered.dropped_by_reason.items() if v > 0
        },
        raw_candidate_count=len(recall_pool.candidates),
        filtered_count=len(filtered.surviving),
        returned_count=returned_count,
    )


def _generate_expansion_hints(
    ctx: QueryContext,
    hits: list[WitnessedHit],
    gap_report: GapReport,
    confidence_ceiling: float,
) -> list[ExpansionHint]:
    """Produce 0..N concrete next-call suggestions.

    Hints are generated by examining the report itself — what's the
    operator likely to want next given this result?
    """
    hints: list[ExpansionHint] = []

    # Hint 1: confidence ceiling is low; suggest broadening filters
    if confidence_ceiling < 0.5 and ctx.stakes == "high":
        hints.append(ExpansionHint(
            action="lower_stakes",
            arg="medium",
            rationale=(
                f"confidence ceiling {confidence_ceiling:.2f} is low; "
                f"some atoms may have been filtered by the high-stakes "
                f"confidence floor of 0.7"
            ),
        ))

    # Hint 2: untrusted_source_high_stakes dropped a lot
    drop_untrusted = gap_report.constitutional_drops.get(
        "untrusted_source_high_stakes", 0
    )
    if drop_untrusted >= 3 and not ctx.allow_pending:
        hints.append(ExpansionHint(
            action="allow_pending",
            arg=None,
            rationale=(
                f"{drop_untrusted} LLM-source atom(s) excluded; if any may "
                f"be relevant, set allow_pending=True"
            ),
        ))

    # Hint 3: bitemporal frame is narrow and dropped atoms
    drop_bitemporal = gap_report.constitutional_drops.get(
        "bitemporal_out_of_frame", 0
    )
    if drop_bitemporal > 0:
        hints.append(ExpansionHint(
            action="broaden_bitemporal",
            arg="remove as_known_at",
            rationale=(
                f"{drop_bitemporal} atom(s) outside the bitemporal frame; "
                f"remove the as_known_at constraint to see them"
            ),
        ))

    # Hint 4: dense or graph wasn't active — suggest fixing
    if "dense" in gap_report.inactive_retrievers:
        hints.append(ExpansionHint(
            action="search_specific_channel",
            arg=None,
            rationale=(
                "dense retriever was inactive; ensure the embed model "
                "is loaded (sov doctor) for full retrieval coverage"
            ),
        ))

    # Hint 5: top hit has a rich provenance chain not all in the pool
    if hits and len(hits[0].provenance_breadcrumb) >= 3:
        top = hits[0]
        hints.append(ExpansionHint(
            action="walk_provenance_of",
            arg=top.atom_id,
            rationale=(
                f"top hit {top.atom_id[:8]} has a provenance chain of "
                f"{len(top.provenance_breadcrumb)}; walking it may surface "
                f"causally-linked context"
            ),
        ))

    return hints


# ─────────────────────────────────────────────────────────────────────────
# Public assembly entry point
# ─────────────────────────────────────────────────────────────────────────


def assemble(
    conn: sqlite3.Connection,
    ctx: QueryContext,
    recall_pool: RecallPool,
    filtered: FilteredPool,
    reranked: RerankedPool,
    *,
    top_k: int = 5,
) -> RetrievalReport:
    """Build the final RetrievalReport from all prior stages' outputs.

    The assembly stage is deterministic — given identical inputs from
    the prior stages, it produces identical output. All randomness and
    model-derived stochasticity is upstream; this stage just packages.
    """
    top_triples = reranked.scored[:top_k]

    hits: list[WitnessedHit] = []
    for row, cand, score in top_triples:
        breadcrumb = _build_breadcrumb(conn, row.atom_id)
        surfaced_by: set[str] = set()
        if cand.lexical_rank is not None:
            surfaced_by.add("lexical")
        if cand.dense_rank is not None:
            surfaced_by.add("dense")
        if cand.graph_rank is not None:
            surfaced_by.add("graph")
        hits.append(WitnessedHit(
            atom_id=row.atom_id,
            summary=row.summary,
            atom_type=row.type,
            created_at=row.created_at,
            created_by_actor=row.created_by_actor,
            confidence=row.confidence,
            score=score,
            provenance_breadcrumb=breadcrumb,
            surfaced_by=frozenset(surfaced_by),
        ))

    # Confidence ceiling: MIN across returned hits (worst-case rule)
    if hits:
        confidence_ceiling = min(h.confidence for h in hits)
    else:
        confidence_ceiling = 0.0

    gap_report = _build_gap_report(recall_pool, filtered, len(hits))
    hints = _generate_expansion_hints(ctx, hits, gap_report, confidence_ceiling)

    # Collected trace from every stage
    trace = list(recall_pool.notes) + list(reranked.notes)

    return RetrievalReport(
        hits=hits,
        confidence_ceiling=confidence_ceiling,
        gap_report=gap_report,
        expansion_hints=hints,
        trace=trace,
        context=ctx,
        semantic_source=reranked.semantic_source,
    )


__all__ = [
    "WitnessedHit",
    "GapReport",
    "ExpansionAction",
    "ExpansionHint",
    "RetrievalReport",
    "assemble",
]
