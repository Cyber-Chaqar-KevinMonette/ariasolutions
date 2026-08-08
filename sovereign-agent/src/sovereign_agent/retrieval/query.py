"""
╔══════════════════════════════════════════════════════════════════════════╗
║  retrieval/query.py — Stage 1: query understanding                      ║
║  v0.2.28.0                                                                ║
║                                                                           ║
║  THE GAP IN STANDARD RAG                                                 ║
║                                                                           ║
║    Off-the-shelf RAG treats the query as a self-contained string. It   ║
║    embeds it, searches, returns results. The query is interpreted      ║
║    *alone*, divorced from who is asking and what they are doing right ║
║    now.                                                                  ║
║                                                                           ║
║    Aria already knows: the operator's current focus, mood, active      ║
║    goals, open intentions. She has bitemporal storage so queries can  ║
║    address "what was true on date X." She has the constitutional      ║
║    distinction between operator-verified atoms and LLM-proposed ones. ║
║                                                                           ║
║    A query that ignores this context throws away signal her substrate ║
║    has already collected. This module makes that context first-class. ║
║                                                                           ║
║  WHAT THIS PRODUCES                                                      ║
║                                                                           ║
║    A QueryContext bundle that downstream stages consume:                ║
║                                                                           ║
║      • literal           — the operator's exact words                  ║
║      • normalized        — case-folded, NFC-normalized, ws-collapsed   ║
║      • aria_focus        — current_focus + active_goals (anchors)      ║
║      • intent            — one of six categorized intents              ║
║      • stakes            — low | medium | high (auto-detected)         ║
║      • valid_at          — bitemporal: when in the world?              ║
║      • as_known_at       — bitemporal: as known when?                  ║
║      • channel_weights   — per-channel weight by intent                ║
║      • allow_pending     — whether LLM-source atoms are allowed        ║
║                                                                           ║
║  AUTHORITY                                                               ║
║                                                                           ║
║    This module is purely Tier 0. It reads aria.load_state() and        ║
║    computes a context bundle. It does not touch the atoms.db rows     ║
║    themselves; that is recall's job.                                  ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


# Six categorized intents. Each carries a different mix of trust and recency
# preferences. The categorization is structured, not free-form.
QueryIntent = Literal[
    "factual",          # "what is X?" — wants stable, high-confidence atoms
    "decision_support", # "should I do Y?" — wants ground truth, high stakes
    "exploration",      # "tell me about Z" — wants breadth, allows speculation
    "conversational",   # "how am I doing?" — wants recent, focus-aligned
    "debug",            # "why did W happen?" — wants provenance, traces
    "reflective",       # "what have I learned?" — wants lessons + insights
]


StakesLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class BitemporalFrame:
    """The two time axes for a query.

    ``valid_at``  — when in the world is the question about?
    ``as_known_at`` — at what point in Aria's history is the answer sought?

    Default: both are NOW. The "as known at" axis is the one most queries
    actually want to override: "what did I think about this on 2026-03-15?"
    is a question about the same world-state but Aria's prior knowledge of
    it.

    For "what was true on 2026-03-15 about something I know now?" set
    ``valid_at`` and leave ``as_known_at`` at None.
    """
    valid_at: str | None = None      # ISO 8601 UTC, or None for "now"
    as_known_at: str | None = None   # ISO 8601 UTC, or None for "now"

    @property
    def is_default(self) -> bool:
        return self.valid_at is None and self.as_known_at is None


@dataclass(frozen=True)
class QueryContext:
    """Everything downstream stages need to know about *this query*.

    A QueryContext is immutable — once built it travels unchanged through
    recall, filter, rerank, and assembly. Mutation would mean the stages
    could rewrite each other's assumptions, which is exactly the kind of
    spaghetti that this layering prevents.
    """

    # The query itself
    literal: str
    normalized: str

    # Who is asking
    aria_focus: str = ""              # operator's current_focus from AriaState
    active_goals: int = 0             # how many goals are active right now
    open_intentions: int = 0          # how many intentions are open

    # What kind of query
    intent: QueryIntent = "exploration"
    stakes: StakesLevel = "medium"

    # When the question is about and as-of-when
    bitemporal: BitemporalFrame = field(default_factory=BitemporalFrame)

    # Per-channel weights for recall fusion. Higher = pull more from this channel.
    channel_weights: dict[str, float] = field(default_factory=dict)

    # Policy: include atoms whose created_by.actor is "llm" with low confidence?
    # Default False on high stakes; True on exploration.
    allow_pending: bool = True

    # The anchor atoms — atoms identified by the focus state that should
    # seed the graph-recall walk. Empty if focus is empty.
    focus_anchor_terms: tuple[str, ...] = ()


# ─────────────────────────────────────────────────────────────────────────
# Intent detection — narrow, structured rules; no LLM call
# ─────────────────────────────────────────────────────────────────────────


# Each entry: (intent, set of keywords that strongly suggest this intent)
# These are signals, not certainties. The default if nothing matches is
# "exploration" — the most permissive intent.
#
# Ordering encodes priority. Debug comes before decision_support because
# "why did the deploy fail" contains "deploy" but is unambiguously a
# debug question. Reflective comes before conversational for the same
# reason — "what have I learned today" is reflective even though "today"
# could look conversational.
_INTENT_SIGNALS: tuple[tuple[QueryIntent, frozenset[str]], ...] = (
    ("debug", frozenset({
        "why did", "what went wrong", "diagnose", "trace", "stack",
        "error", "failure", "broken", "regression", "bug",
        "what caused", "why does", "why is",
    })),
    ("reflective", frozenset({
        "what have i learned", "lessons", "what do i know", "reflect",
        "retrospect", "look back", "have i grown",
    })),
    ("decision_support", frozenset({
        "should i", "should we", "do i", "decide", "choose", "pick",
        "ship", "approve", "commit", "deploy", "buy", "sell", "go ahead",
    })),
    ("conversational", frozenset({
        "how am i", "how are you", "how was", "tell me about today",
        "what's on my mind", "what's up", "how do you feel",
    })),
    ("factual", frozenset({
        "what is", "what are", "define", "definition of", "who is",
        "when did", "where is", "how many",
    })),
)


def _detect_intent(normalized_query: str) -> QueryIntent:
    """Detect the query intent from the normalized text.

    Rule-based on purpose: an LLM call here would (a) be slow, (b) be
    circular (asking the LLM to classify so the LLM can answer), and
    (c) introduce a fragile dependency on a model that may not be loaded.
    Rules are honest about their limitations and ship today.
    """
    text = normalized_query.lower()
    # The order in _INTENT_SIGNALS encodes priority: decision_support
    # checked first because it's the highest-stakes category.
    for intent, signals in _INTENT_SIGNALS:
        for phrase in signals:
            if phrase in text:
                return intent
    return "exploration"


# Stakes detection — independent of intent. Decisions, irreversible actions,
# and authority escalations are all high-stakes regardless of phrasing.
_HIGH_STAKES_MARKERS = frozenset({
    "irreversible", "permanent", "production", "live", "real users",
    "money", "payment", "billing", "delete", "destroy", "permanent",
    "ship", "deploy", "approve", "authorize", "sign off",
    "tier 3", "tier-3", "tier3",
})

_LOW_STAKES_MARKERS = frozenset({
    "scratch", "draft", "exploration", "brainstorm", "rough",
    "just curious", "wondering",
})


def _detect_stakes(normalized_query: str, intent: QueryIntent) -> StakesLevel:
    """Detect stakes level. LOW markers checked BEFORE HIGH markers.

    Why low-before-high: the operator's explicit framing ("brainstorm",
    "just curious", "wondering") is a conscious low-stakes declaration
    that dominates implicit content cues. "Brainstorm deploy failures"
    is brainstorming about deployment — the operator is signaling
    exploratory mode even though the topic is deployment. The high-stakes
    markers fire when the question is *about* doing something at high
    stakes, not when the topic merely involves a high-stakes domain.
    """
    text = normalized_query.lower()
    base: StakesLevel = "medium"

    # Low-stakes framing dominates — the operator has explicitly told us
    # this is exploratory. Their conscious framing wins over topic words.
    for marker in _LOW_STAKES_MARKERS:
        if marker in text:
            return "low"

    # No low-stakes framing → escalate if any high-stakes markers fire
    for marker in _HIGH_STAKES_MARKERS:
        if marker in text:
            return "high"

    # Default behavior by intent
    if intent == "decision_support":
        return "high"
    return base


# ─────────────────────────────────────────────────────────────────────────
# Channel weights per intent — the typed-memory advantage
# ─────────────────────────────────────────────────────────────────────────


# Default weight is 1.0 (no preference). Channels not listed get 1.0.
# These weights are an opinion — they say "for this kind of question,
# pull more from these channels and less from those." The numbers are
# tunable; the structure is the contract.
_CHANNEL_WEIGHTS: dict[QueryIntent, dict[str, float]] = {
    "factual": {
        "insights": 1.5, "lessons": 1.3, "specialist": 1.5,
        "humor": 0.3, "emotions": 0.3, "intuition": 0.4,
    },
    "decision_support": {
        "lessons": 2.0, "insights": 1.5, "reasoning": 1.8,
        "commitments": 1.5, "gaps": 1.5,
        "humor": 0.2, "emotions": 0.5,
    },
    "exploration": {
        "intuition": 1.3, "personalities": 1.2,
        # broad — no strong down-weighting
    },
    "conversational": {
        "context": 1.8, "emotions": 1.5, "intention": 1.5,
        "personalities": 1.3, "humor": 1.3, "intuition": 1.3,
        "lessons": 0.6,    # less lecture, more conversation
    },
    "debug": {
        "reasoning": 2.0, "lessons": 1.5, "gaps": 1.5,
        "episodes": 1.5,    # debug needs the narrative arc
        "humor": 0.2,
    },
    "reflective": {
        "lessons": 2.0, "insights": 1.8, "reasoning": 1.5,
        "episodes": 1.5, "identity": 1.3,
        "humor": 0.5,
    },
}


def _channel_weights_for_intent(intent: QueryIntent) -> dict[str, float]:
    return dict(_CHANNEL_WEIGHTS.get(intent, {}))


# ─────────────────────────────────────────────────────────────────────────
# Normalization
# ─────────────────────────────────────────────────────────────────────────


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """NFC-normalize, strip RTL overrides, casefold, collapse whitespace.

    Same primitive Aria's people-channel uses for name resolution (per
    v0.2.17 unicode normalization). One canonical form keeps lexical
    search and dense embedding aligned with each other.
    """
    # Strip Unicode bidirectional control characters that can shadow text
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = unicodedata.normalize("NFC", text)
    text = text.casefold()
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


# ─────────────────────────────────────────────────────────────────────────
# Focus anchoring — terms from AriaState used to seed graph recall
# ─────────────────────────────────────────────────────────────────────────


def _extract_anchor_terms(focus: str) -> tuple[str, ...]:
    """Pull noun-like tokens from current_focus to use as graph-walk anchors.

    Conservative: anything longer than 3 chars that isn't a stopword.
    The anchor terms drive the graph-recall stage — atoms matching these
    terms become seed nodes for the provenance walk.
    """
    if not focus:
        return ()
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", focus)
    stopwords = {
        "the", "and", "for", "with", "from", "into", "onto", "but", "not",
        "have", "has", "had", "this", "that", "these", "those", "are",
        "was", "were", "been", "being",
    }
    return tuple(t.lower() for t in tokens if t.lower() not in stopwords)


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


def understand_query(
    *,
    query: str,
    aria_focus: str = "",
    active_goals: int = 0,
    open_intentions: int = 0,
    intent_override: QueryIntent | None = None,
    stakes_override: StakesLevel | None = None,
    valid_at: str | None = None,
    as_known_at: str | None = None,
) -> QueryContext:
    """Build a QueryContext from a raw query and the operator's current state.

    All parameters except ``query`` are optional; the function degrades
    cleanly when the focus state is unavailable (e.g. tests, fresh
    install). Override parameters are for callers who already know what
    they're asking; absent them, the function classifies automatically.

    Bitemporal overrides are passed through unchanged. They are
    intentionally raw ISO strings — the bitemporal module is the
    authority on parsing those, and we don't second-guess it here.
    """
    if not query or not query.strip():
        raise ValueError("query cannot be empty")

    normalized = _normalize(query)
    intent = intent_override or _detect_intent(normalized)
    stakes = stakes_override or _detect_stakes(normalized, intent)

    # High stakes flips allow_pending off — untrusted-input doctrine
    # extends to retrieval. On low/medium stakes, pending atoms are still
    # visible (with their `source=pending` mark intact so downstream can
    # weight them appropriately).
    allow_pending = stakes != "high"

    return QueryContext(
        literal=query,
        normalized=normalized,
        aria_focus=aria_focus,
        active_goals=active_goals,
        open_intentions=open_intentions,
        intent=intent,
        stakes=stakes,
        bitemporal=BitemporalFrame(valid_at=valid_at, as_known_at=as_known_at),
        channel_weights=_channel_weights_for_intent(intent),
        allow_pending=allow_pending,
        focus_anchor_terms=_extract_anchor_terms(aria_focus),
    )


def understand_query_with_aria_state(
    *,
    query: str,
    conn: sqlite3.Connection,
    intent_override: QueryIntent | None = None,
    stakes_override: StakesLevel | None = None,
    valid_at: str | None = None,
    as_known_at: str | None = None,
) -> QueryContext:
    """Convenience wrapper: load AriaState from the DB, then build context.

    Use this from CLI tools and the cockpit, where loading state is
    cheap. Inside the agent loop, prefer the explicit ``understand_query``
    so the loop's own state cache is used.
    """
    from ..aria import load_state

    state = load_state(conn)
    return understand_query(
        query=query,
        aria_focus=state.current_focus,
        active_goals=state.active_goals,
        open_intentions=state.open_intentions,
        intent_override=intent_override,
        stakes_override=stakes_override,
        valid_at=valid_at,
        as_known_at=as_known_at,
    )


def now_iso() -> str:
    """Helper for callers building bitemporal frames."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


__all__ = [
    "QueryIntent",
    "StakesLevel",
    "BitemporalFrame",
    "QueryContext",
    "understand_query",
    "understand_query_with_aria_state",
    "now_iso",
]
