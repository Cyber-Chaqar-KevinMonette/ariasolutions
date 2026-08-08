"""
╔══════════════════════════════════════════════════════════════════════════╗
║  retrieval/filter.py — Stage 3: constitutional + bitemporal filtering   ║
║  v0.2.28.0                                                                ║
║                                                                           ║
║  THE CONSTITUTIONAL LAYER, AT RETRIEVAL TIME                             ║
║                                                                           ║
║    Most RAG systems apply safety policy at the GENERATION stage —      ║
║    the LLM has already seen the untrusted document; the policy is on  ║
║    what the LLM is *allowed to say about it*. This leaks information. ║
║    A model that has seen poisoned text cannot fully unsee it.         ║
║                                                                           ║
║    Aria already has the substrate to do this RIGHT: every atom has a  ║
║    ``created_by.actor`` distinguishing operator-verified content from ║
║    LLM-proposed content (the ``pending`` mark from the people-channel ║
║    doctrine, generalized).                                             ║
║                                                                           ║
║    This module enforces three constitutional filters BEFORE the model ║
║    sees anything:                                                      ║
║                                                                           ║
║      1. ◊ Untrusted-input doctrine                                     ║
║           High-stakes queries get only operator-verified atoms.       ║
║           Low/medium queries can see pending atoms with the mark.     ║
║                                                                           ║
║      2. ◊ Calibrated uncertainty                                       ║
║           Atoms with confidence below a stakes-dependent floor are    ║
║           filtered. Floor is 0.7 on high-stakes, 0.4 on medium, none ║
║           on low.                                                     ║
║                                                                           ║
║      3. ◊ Privacy boundary                                             ║
║           Atoms with policy != "local_only" excluded by default.      ║
║           People-channel and relationship-channel atoms are excluded  ║
║           unless the intent explicitly indicates need.                ║
║                                                                           ║
║  THE BITEMPORAL FILTER                                                   ║
║                                                                           ║
║    If the QueryContext has a non-default bitemporal frame:             ║
║      ``valid_at`` filters by world-state time (which atoms describe   ║
║         facts true at this moment in the world)                       ║
║      ``as_known_at`` filters by Aria's-knowledge time (which atoms    ║
║         did Aria have written by this point)                          ║
║                                                                           ║
║    For the default frame (both None = now/now), no bitemporal filter  ║
║    applies — we return the current head-of-chain view.                ║
║                                                                           ║
║  WHAT GETS RETURNED                                                      ║
║                                                                           ║
║    A FilteredPool with two key fields beyond the obvious:              ║
║      ``dropped_by_reason`` — count of atoms filtered out per reason   ║
║      ``confidence_floor_applied`` — what threshold was active         ║
║                                                                           ║
║    These power the gap report at assembly time: "I would have shown  ║
║    you 12 atoms but 7 were filtered for confidence below 0.7; if you ║
║    want the broader view, ask with stakes=medium."                    ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from .query import QueryContext
from .recall import RecallCandidate, RecallPool


# Confidence floors per stakes level. These are deliberate, not magic numbers.
# - High stakes: 0.7 because going below this means we're showing the model
#   speculation as evidence for a decision; that's where errors compound.
# - Medium: 0.4 because routine work tolerates "this might be true."
# - Low: 0.0 because exploration is the right time to look at fuzzy memories.
_CONFIDENCE_FLOOR = {"high": 0.7, "medium": 0.4, "low": 0.0}


# Channels whose atoms reference people directly. These are filtered out
# unless the query intent suggests personal context is genuinely needed.
# Operator-driven personal queries (intent=conversational + focus mentions
# a person) still get through; this is the default exclusion.
_PRIVATE_CHANNELS = frozenset({"people", "relationships", "people_health"})  # people-health-privacy-d


# Intents that genuinely need personal-channel access
_PERSONAL_INTENT = frozenset({"conversational", "reflective"})


# ─────────────────────────────────────────────────────────────────────────
# Hydration — pull the columns we need to filter
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HydratedRow:
    """One atoms.db row, hydrated with the columns the filter needs.

    Intentionally narrow: only the columns the filter and rerank stages
    actually consume. Assembly stage hydrates the rest (summary, content_ref,
    etc) for the final output. This keeps the filter pass cheap.
    """
    atom_id: str
    type: str
    scope_tags: list[str]
    summary: str
    confidence: float
    policy: str
    created_at: str
    created_by_actor: str   # extracted from created_by JSON
    superseded_at: str | None
    version: int


def _hydrate(
    conn: sqlite3.Connection,
    atom_ids: list[str],
) -> dict[str, HydratedRow]:
    """Fetch hydrated rows for the given atom_ids in one query.

    Returns a dict atom_id → HydratedRow. Atoms that don't exist (e.g.
    came from a stale vec_atoms entry) are simply absent from the result —
    the filter pass treats them as if they were already dropped.
    """
    if not atom_ids:
        return {}

    placeholders = ",".join("?" * len(atom_ids))
    rows = conn.execute(
        f"SELECT atom_id, type, scope_tags, summary, confidence, "
        f"policy, created_at, created_by, superseded_at, version "
        f"FROM atoms WHERE atom_id IN ({placeholders})",
        tuple(atom_ids),
    ).fetchall()

    out: dict[str, HydratedRow] = {}
    for r in rows:
        aid, atype, tags_json, summary, conf, policy, created_at, \
            created_by_json, superseded_at, version = r
        try:
            tags = json.loads(tags_json) if tags_json else []
        except json.JSONDecodeError:
            tags = []
        try:
            cb = json.loads(created_by_json) if created_by_json else {}
        except json.JSONDecodeError:
            cb = {}
        out[aid] = HydratedRow(
            atom_id=aid,
            type=atype,
            scope_tags=list(tags) if isinstance(tags, list) else [],
            summary=summary,
            confidence=float(conf),
            policy=policy,
            created_at=created_at,
            created_by_actor=str(cb.get("actor", "unknown")),
            superseded_at=superseded_at,
            version=int(version),
        )
    return out


# ─────────────────────────────────────────────────────────────────────────
# The filter — applies each policy and counts drops by reason
# ─────────────────────────────────────────────────────────────────────────


# Reasons an atom can be dropped. The set is small on purpose — every
# new reason is a new policy and should be a deliberate addition.
DropReason = str   # see _ALL_REASONS for the valid values

_ALL_REASONS = frozenset({
    "superseded",
    "below_confidence_floor",
    "untrusted_source_high_stakes",
    "private_channel_excluded",
    "non_local_policy",
    "bitemporal_out_of_frame",
    "row_missing",
})


@dataclass
class FilteredPool:
    """Output of the filter stage.

    ``surviving`` is the set of (candidate, hydrated) pairs that passed.
    ``hydrated`` is keyed by atom_id and provided so downstream stages
    don't need to re-query.
    ``dropped_by_reason`` is the count of atoms removed per policy —
    powers the gap report at assembly time.
    """
    surviving: list[tuple[RecallCandidate, HydratedRow]]
    hydrated: dict[str, HydratedRow]
    dropped_by_reason: dict[str, int] = field(default_factory=dict)
    confidence_floor_applied: float = 0.0
    allow_pending_active: bool = True
    private_channels_included: bool = False


def _is_atom_in_bitemporal_frame(
    row: HydratedRow, ctx: QueryContext
) -> bool:
    """Check whether an atom fits the QueryContext's bitemporal frame.

    The minimal honest semantics: if ``as_known_at`` is set, the atom
    must have been created on or before that time. (Aria did not know
    this atom yet at that point in her own history.)

    The ``valid_at`` axis would need per-channel bitemporal columns
    (which not all channels have); when the channel doesn't carry
    those columns we let the atom through. This is bitemporal
    *correctness with honest degradation* — we filter when we can,
    we don't lie about what we can't filter.
    """
    if ctx.bitemporal.is_default:
        return True
    if ctx.bitemporal.as_known_at is not None:
        if row.created_at > ctx.bitemporal.as_known_at:
            return False
    # The valid_at axis is per-channel and not in the base atoms row;
    # we honor it where the channel surfaces it but cannot enforce here.
    return True


def constitutional_filter(
    conn: sqlite3.Connection,
    pool: RecallPool,
    ctx: QueryContext,
) -> FilteredPool:
    """Apply all constitutional and bitemporal filters to a RecallPool.

    Each surviving candidate is paired with its HydratedRow so downstream
    stages don't need to re-query. Drops are counted by reason; the
    counts power the gap report.
    """
    atom_ids = [c.atom_id for c in pool.candidates]
    hydrated = _hydrate(conn, atom_ids)

    floor = _CONFIDENCE_FLOOR.get(ctx.stakes, 0.0)
    private_ok = ctx.intent in _PERSONAL_INTENT

    surviving: list[tuple[RecallCandidate, HydratedRow]] = []
    dropped: dict[str, int] = {r: 0 for r in _ALL_REASONS}

    for candidate in pool.candidates:
        row = hydrated.get(candidate.atom_id)
        if row is None:
            dropped["row_missing"] += 1
            continue

        # 1. Head-of-chain only (architecture invariant)
        if row.superseded_at is not None:
            dropped["superseded"] += 1
            continue

        # 2. Confidence floor (calibrated_uncertainty commitment)
        if row.confidence < floor:
            dropped["below_confidence_floor"] += 1
            continue

        # 3. Untrusted source on high stakes (untrusted-input doctrine)
        is_pending = row.created_by_actor == "llm"
        if is_pending and not ctx.allow_pending:
            dropped["untrusted_source_high_stakes"] += 1
            continue

        # 4. Policy (privacy)
        if row.policy != "local_only":
            dropped["non_local_policy"] += 1
            continue

        # 5. Private channels (people/relationships) — gated by intent
        if not private_ok:
            tag_set = set(row.scope_tags)
            if tag_set & _PRIVATE_CHANNELS:
                dropped["private_channel_excluded"] += 1
                continue

        # 6. Bitemporal frame
        if not _is_atom_in_bitemporal_frame(row, ctx):
            dropped["bitemporal_out_of_frame"] += 1
            continue

        surviving.append((candidate, row))

    return FilteredPool(
        surviving=surviving,
        hydrated=hydrated,
        dropped_by_reason=dropped,
        confidence_floor_applied=floor,
        allow_pending_active=ctx.allow_pending,
        private_channels_included=private_ok,
    )


__all__ = [
    "HydratedRow",
    "FilteredPool",
    "DropReason",
    "constitutional_filter",
]
