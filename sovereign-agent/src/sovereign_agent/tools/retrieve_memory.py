"""retrieve_memory — Tier 0 (read-only, sovereign retrieval).

Exposes the full Sovereign Retrieval Pipeline (``sovereign_agent.retrieval``)
to the agent loop as a callable tool. Differs from ``memory_search`` (which
uses the substrate ``memory/retrieval.hybrid_search``) in three important
ways:

  • Constitutional filtering — LLM-source atoms excluded on high-stakes
    queries; private channels guarded by intent.
  • Bitemporal awareness — caller can pass ``as_known_at`` to ask "what
    did I know at this point in my history?"
  • Witnessed output — every hit carries its full epistemic context:
    score breakdown, provenance breadcrumb, source actor, confidence.

The tool also surfaces the report's gap analysis and expansion hints so
the model can decide whether to call again with broader parameters.

Authority: Tier 0 — pure read.
"""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..db import open_atoms_db
from ..ollama_client import OllamaClient
from ..retrieval import retrieve_from_state
from .base import Tool, ToolResult


class _Args(BaseModel):
    query: str = Field(
        min_length=1,
        description=(
            "The retrieval query in natural language. Free-form prose is "
            "fine — the pipeline tokenizes, normalizes, and classifies it. "
            "Examples: 'should I ship the rollback to production?', 'what "
            "have I learned about deployment in the last month?'"
        ),
    )
    top_k: int = Field(
        default=5, ge=1, le=20,
        description="How many top-ranked witnessed hits to return.",
    )
    intent_override: str | None = Field(
        default=None,
        description=(
            "Bypass auto-classification. One of: 'factual', 'decision_support', "
            "'exploration', 'conversational', 'debug', 'reflective'. Leave "
            "unset for normal use."
        ),
    )
    stakes_override: str | None = Field(
        default=None,
        description=(
            "Bypass auto-detection. One of: 'low', 'medium', 'high'. High "
            "filters out LLM-source atoms and applies a 0.7 confidence floor. "
            "Set 'high' when grounding a decision the operator will act on."
        ),
    )
    as_known_at: str | None = Field(
        default=None,
        description=(
            "Bitemporal: as Aria knew when? ISO 8601 UTC timestamp (e.g. "
            "'2026-03-15T00:00:00.000000Z'). Limits results to atoms created "
            "on or before this point. Leave unset for current-knowledge view."
        ),
    )


class RetrieveMemoryTool(Tool[_Args]):
    name = "retrieve_memory"
    tier = 0
    description = (
        "Run the Sovereign Retrieval Pipeline against atoms.db. Returns "
        "the top-k witnessed hits (each with summary, confidence, source actor, "
        "score breakdown, and provenance breadcrumb), plus a confidence ceiling, "
        "a gap report listing what was filtered or missing, and expansion hints "
        "if the result set is thin. Prefer this over memory_search when you "
        "need ground truth for a decision — the constitutional layer filters "
        "untrusted-source atoms on high stakes BEFORE you see them. FAILURE "
        "MODES: ollama unreachable (degrades to RRF-only retrieval, still "
        "returns hits); atoms.db not initialized; no hits found (returns empty "
        "report with gap_report and expansion_hints)."
    )
    failure_modes = (
        "ollama_unreachable",
        "atoms_db_missing",
        "no_hits",
    )
    Args = _Args

    def __init__(self, client: OllamaClient | None = None) -> None:
        self._client = client or OllamaClient()

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        # Try to build an embedder closure. If Ollama is unreachable, we pass
        # None and the pipeline degrades to lexical+graph recall with RRF
        # reranking. This is documented honest degradation, not silent failure.
        embedder = await self._build_embedder()

        def _retrieve() -> dict:
            conn = open_atoms_db()
            try:
                report = retrieve_from_state(
                    query=args.query,
                    conn=conn,
                    intent_override=args.intent_override,
                    stakes_override=args.stakes_override,
                    as_known_at=args.as_known_at,
                    embedder=embedder,
                    top_k=args.top_k,
                )
            finally:
                conn.close()
            return _serialize_report(report)

        try:
            payload = await asyncio.to_thread(_retrieve)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"retrieval failed: {e}")

        return ToolResult(
            ok=True,
            output=payload,
            metadata={
                "hits_returned": len(payload["hits"]),
                "confidence_ceiling": payload["confidence_ceiling"],
                "semantic_source": payload["semantic_source"],
                "expansion_hints_count": len(payload["expansion_hints"]),
            },
        )

    async def _build_embedder(self):
        """Return an embedder closure or None if Ollama isn't reachable.

        The embedder is called synchronously by the pipeline from a worker
        thread; we wrap the async client.embed call with asyncio.run inside
        the closure. If the initial probe call fails, return None and let
        the pipeline degrade to lexical+graph recall.
        """
        # Quick reachability check — if this fails, dense will be skipped.
        try:
            test_vec = await self._client.embed(
                model=SETTINGS.embed_model, prompt="probe"
            )
            if not test_vec:
                return None
        except Exception:  # noqa: BLE001
            return None

        client = self._client
        embed_model = SETTINGS.embed_model

        def _embed_sync(text: str) -> list[float] | None:
            try:
                return asyncio.run(
                    client.embed(model=embed_model, prompt=text)
                )
            except RuntimeError:
                # If we're already inside an event loop (shouldn't happen
                # since the pipeline calls us via to_thread, but defensive)
                return None
            except Exception:
                return None

        return _embed_sync


def _serialize_report(report) -> dict:
    """Convert a RetrievalReport into JSON-serializable form for the tool's
    output channel. The shape is stable: callers can rely on these keys.
    """
    return {
        "hits": [
            {
                "atom_id": h.atom_id,
                "summary": h.summary,
                "atom_type": h.atom_type,
                "created_at": h.created_at,
                "created_by_actor": h.created_by_actor,
                "confidence": round(h.confidence, 4),
                "score": {
                    "semantic": round(h.score.semantic, 4),
                    "provenance": round(h.score.provenance, 4),
                    "recency_confidence": round(h.score.recency_confidence, 4),
                    "fused": round(h.score.fused, 4),
                },
                "provenance_breadcrumb": list(h.provenance_breadcrumb),
                "surfaced_by": sorted(h.surfaced_by),
            }
            for h in report.hits
        ],
        "confidence_ceiling": round(report.confidence_ceiling, 4),
        "semantic_source": report.semantic_source,
        "gap_report": {
            "empty_retrievers": list(report.gap_report.empty_retrievers),
            "inactive_retrievers": list(report.gap_report.inactive_retrievers),
            "constitutional_drops": dict(report.gap_report.constitutional_drops),
            "raw_candidate_count": report.gap_report.raw_candidate_count,
            "filtered_count": report.gap_report.filtered_count,
            "returned_count": report.gap_report.returned_count,
        },
        "expansion_hints": [
            {
                "action": h.action,
                "arg": h.arg,
                "rationale": h.rationale,
            }
            for h in report.expansion_hints
        ],
        "intent": report.context.intent if report.context else "unknown",
        "stakes": report.context.stakes if report.context else "unknown",
        "trace": list(report.trace),
    }
