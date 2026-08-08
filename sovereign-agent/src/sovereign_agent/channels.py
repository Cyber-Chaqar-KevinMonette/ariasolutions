"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels.py — The modular memory channel substrate                      ║
║  v0.2.14 · Aria-Sovereign-V1                                              ║
║                                                                           ║
║  A "channel" is a typed view over the atoms store with channel-specific  ║
║  semantics. Every channel:                                                ║
║                                                                           ║
║    • Inherits from MemoryChannel (this file)                              ║
║    • Carries a ChannelSpec (name, authority tier, write contract)         ║
║    • Owns its tag in atoms.scope_tags ({"channel": "<name>", ...})       ║
║    • Can implement custom hydration on top of the base atom shape        ║
║                                                                           ║
║  WHY THIS MATTERS                                                         ║
║                                                                           ║
║  Memory in one place is brittle. A financial query and an emotional      ║
║  recall and a humor callback should not all share the same retrieval     ║
║  policy or the same write authority. Channels separate these concerns    ║
║  while keeping a single index (atoms FTS + vec + RRF + palace).          ║
║                                                                           ║
║  Aria can register new channels at runtime via ``register_channel``.     ║
║  The system grows its own organs.                                        ║
║                                                                           ║
║  MOS ALIGNMENT                                                            ║
║                                                                           ║
║    • Append-only events (canon §10): every channel write emits an event ║
║    • Calibrated uncertainty (Law 5): each atom has confidence ∈ [0,1]    ║
║    • Authority tiers (canon §22): each channel declares its tier        ║
║    • Idempotency-as-contract (canon §16): writes accept idempotency_id   ║
║    • Untrusted-input doctrine (canon §18.2): channels treat content as   ║
║      data, never as instructions                                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal


# ─── Authority tiers (MOS canon §22) ────────────────────────────────────────


AuthorityTier = Literal[0, 1, 2, 3, 4]
"""
0 — Read-only, no side effects (Aria recalls)
1 — Reversible writes, bounded scope (humor, emotions, intuition)
2 — Persistent changes, external calls (goals, context, specialist, lessons)
3 — Irreversible / financial / PII (financial ledger, identity)
4 — Cross-system, multi-agent orchestration (none yet — reserved)
"""


# ─── Channel specification ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ChannelSpec:
    """One channel's contract — what it stores, how, with what authority.

    Instances are frozen because spec drift between sessions is a known
    failure mode. Specs are read-only after registration.
    """
    name: str                              # 'financial', 'goals', 'humor'...
    description: str                       # human-readable purpose
    authority_tier: AuthorityTier          # MOS canon §22
    default_confidence: float = 0.7        # base confidence for new atoms
    requires_idempotency: bool = False     # True for Tier 3+
    introduced_in: str = "0.2.14"
    voice: str = ""                        # short tone/voice descriptor


# ─── The channel base class ─────────────────────────────────────────────────


class MemoryChannel:
    """Base class for all memory channels.

    Subclasses override ``write_atom`` for channel-specific shape and may
    override ``hydrate`` to enrich search results with channel data
    (e.g., financial channel attaches running balance).
    """

    spec: ChannelSpec  # subclasses MUST set this as a class attribute

    def __init__(self, conn: sqlite3.Connection):
        if not hasattr(self, "spec") or self.spec is None:
            raise TypeError(
                f"{type(self).__name__}: ChannelSpec must be set as "
                f"class attribute"
            )
        self.conn = conn

    # ── Write path ────────────────────────────────────────────────────

    def write_atom(
        self,
        *,
        summary: str,
        content: dict[str, Any] | None = None,
        confidence: float | None = None,
        parents: list[str] | None = None,
        idempotency_id: str | None = None,
        extra_scope: dict[str, Any] | None = None,
        actor: str = "aria",
    ) -> str:
        """Write an atom to this channel. Returns the atom_id.

        Idempotency: if the channel requires_idempotency and this id has
        been seen before, returns the existing atom_id without
        re-writing. Otherwise idempotency_id is just a tag.

        Authority: callers are responsible for upholding the channel's
        authority tier. Tier 3+ writes should pass through an explicit
        operator confirmation BEFORE invoking this method.
        """
        if self.spec.requires_idempotency and not idempotency_id:
            raise ValueError(
                f"channel {self.spec.name!r} requires idempotency_id "
                f"(Tier {self.spec.authority_tier})"
            )

        # Idempotency check — for tier-3+ channels.
        if idempotency_id:
            existing = _find_by_idempotency(
                self.conn, self.spec.name, idempotency_id,
            )
            if existing:
                return existing

        atom_id = _mint_atom_id(self.spec.name, summary, idempotency_id)
        confidence = confidence if confidence is not None else self.spec.default_confidence
        confidence = max(0.0, min(1.0, confidence))

        scope_tags = {"channel": self.spec.name}
        if idempotency_id:
            scope_tags["idempotency_id"] = idempotency_id
        if extra_scope:
            scope_tags.update(extra_scope)

        content_ref = {"kind": "channel", "channel": self.spec.name}
        if content:
            content_ref.update({"data": content})

        self.conn.execute(
            "INSERT OR IGNORE INTO atoms("
            "atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by, scope_tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                atom_id,
                self.spec.name,                              # type = channel name
                summary[:1000],                              # MOS atom schema cap
                json.dumps(content_ref, sort_keys=True),
                json.dumps([]),
                json.dumps(parents or []),
                confidence,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                json.dumps({"actor": actor, "channel": self.spec.name}),
                json.dumps(scope_tags, sort_keys=True),
            ),
        )
        # Only commit if we are NOT inside an enclosing transaction. A
        # subclass that wraps several writes in BEGIN IMMEDIATE (e.g.
        # FinancialChannel.record) would have its atomicity broken if
        # we committed here. The python sqlite3 driver auto-begins on
        # the first write, so in_transaction is True iff there's an
        # uncommitted write — including ones our caller started.
        # We use the `_in_outer_tx` sentinel so subclass code can opt in
        # explicitly when needed.
        if not getattr(self, "_in_outer_tx", False):
            self.conn.commit()

        # Emit an event for observability (MOS §17 — observability contract).
        try:
            from .events import emit_event
            emit_event(
                "channel-write-d", plane="data",
                trace_id=f"channel:{self.spec.name}:{atom_id}",
                payload={
                    "channel": self.spec.name, "atom_id": atom_id,
                    "actor": actor, "tier": self.spec.authority_tier,
                    "idempotency_id": idempotency_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            # Don't crash the write if the events plane is unavailable, but
            # surface the failure so silent observability rot is detectable.
            import sys
            print(
                f"[channel:{self.spec.name}] event emit failure: {exc!r}",
                file=sys.stderr,
            )

        return atom_id

    # ── Read path ─────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        query_vec: list[float] | None = None,
    ) -> list["ChannelHit"]:
        """Channel-scoped hybrid search. Filters by channel scope_tag."""
        # Use the existing memory.retrieval.hybrid_search and post-filter.
        # This is the same pattern as memory_namespaces.search_in_project.
        from .memory.retrieval import hybrid_search

        raw = hybrid_search(self.conn, query, query_vec=query_vec, top_k=top_k * 3)
        out: list[ChannelHit] = []
        for hit in raw:
            scope = _scope_tags_for_atom(self.conn, hit.atom_id)
            if scope.get("channel") != self.spec.name:
                continue
            out.append(ChannelHit(
                atom_id=hit.atom_id,
                channel=self.spec.name,
                summary=hit.summary,
                score=getattr(hit, "fused_score", 0.0),
                confidence=getattr(hit, "confidence", 0.0),
                hydrated=self.hydrate(hit.atom_id),
            ))
            if len(out) >= top_k:
                break
        return out

    def hydrate(self, atom_id: str) -> dict[str, Any]:
        """Channel-specific enrichment.

        Override this to attach computed data (balances, freshness,
        correlations…) to a recall result. Default returns the raw
        content_ref data block.
        """
        row = self.conn.execute(
            "SELECT content_ref, scope_tags FROM atoms WHERE atom_id = ?",
            (atom_id,),
        ).fetchone()
        if row is None:
            return {}
        try:
            ref = json.loads(row[0] or "{}")
        except json.JSONDecodeError:
            ref = {}
        return ref.get("data", {})

    # ── Listing ───────────────────────────────────────────────────────

    def list_atoms(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Recent atoms in this channel, newest first."""
        rows = self.conn.execute(
            "SELECT atom_id, summary, confidence, created_at, scope_tags "
            "FROM atoms WHERE type = ? "
            "AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (self.spec.name, limit),
        ).fetchall()
        return [
            {
                "atom_id": r[0], "summary": r[1],
                "confidence": r[2], "created_at": r[3],
                "scope_tags": _safe_json(r[4]),
            }
            for r in rows
        ]


# ─── Hit record returned by channel search ──────────────────────────────────


@dataclass
class ChannelHit:
    """One result from a channel search."""
    atom_id: str
    channel: str
    summary: str
    score: float
    confidence: float
    hydrated: dict[str, Any]


# ─── Channel registry ──────────────────────────────────────────────────────


_REGISTRY: dict[str, type[MemoryChannel]] = {}


def register_channel(channel_class: type[MemoryChannel]) -> type[MemoryChannel]:
    """Register a channel class. Use as a decorator or call directly.

    Idempotent: registering the same class twice with the same name is a
    no-op. Two DIFFERENT classes claiming the same name raises ValueError.
    """
    spec = getattr(channel_class, "spec", None)
    if spec is None:
        raise TypeError(
            f"{channel_class.__name__}: must set 'spec: ChannelSpec' as "
            f"class attribute before registration"
        )
    existing = _REGISTRY.get(spec.name)
    if existing is not None and existing is not channel_class:
        raise ValueError(
            f"channel {spec.name!r} is already registered to "
            f"{existing.__name__}; refusing to overwrite"
        )
    _REGISTRY[spec.name] = channel_class
    return channel_class


def list_channels() -> list[ChannelSpec]:
    """All registered channels' specs, sorted by name."""
    return [_REGISTRY[k].spec for k in sorted(_REGISTRY.keys())]


def get_channel(name: str, conn: sqlite3.Connection) -> MemoryChannel:
    """Instantiate the channel class for ``name``. Raises KeyError if missing."""
    if name not in _REGISTRY:
        raise KeyError(
            f"unknown channel {name!r}; "
            f"available: {sorted(_REGISTRY.keys())}"
        )
    return _REGISTRY[name](conn)


def _registry_dict_for_tests() -> dict[str, type[MemoryChannel]]:
    """Test-only accessor — never use in production code."""
    return dict(_REGISTRY)


# ─── Universal recall ──────────────────────────────────────────────────────


def universal_recall(
    conn: sqlite3.Connection,
    query: str,
    *,
    top_k_per_channel: int = 5,
    channels: list[str] | None = None,
    query_vec: list[float] | None = None,
) -> dict[str, list[ChannelHit]]:
    """Search across all registered channels (or a named subset).

    Returns ``{channel_name: [hits...], ...}`` — one bucket per channel
    that produced any results. Empty buckets are omitted.

    This is Aria's primary recall surface. When she needs context, she
    calls this; when the operator asks "what do you know about X," this
    answers.
    """
    targets = channels if channels else sorted(_REGISTRY.keys())
    out: dict[str, list[ChannelHit]] = {}
    for channel_name in targets:
        if channel_name not in _REGISTRY:
            continue
        try:
            channel = get_channel(channel_name, conn)
            hits = channel.search(
                query, top_k=top_k_per_channel, query_vec=query_vec,
            )
            if hits:
                out[channel_name] = hits
        except Exception as exc:  # noqa: BLE001
            # One channel's failure must not break universal recall, but
            # silent failure hides drift. Log and continue.
            import sys
            print(
                f"[universal_recall] channel {channel_name!r} failed: {exc!r}",
                file=sys.stderr,
            )
            continue
    return out


# ─── Internal helpers ──────────────────────────────────────────────────────


def _mint_atom_id(channel: str, summary: str, idempotency_id: str | None) -> str:
    """Deterministic id when idempotency_id is supplied, ULID otherwise.

    Deterministic ids let retries land on the same row (MOS canon §16).
    Non-deterministic ids use ULIDs — monotonic, sortable, collision-safe
    under bursty writes (the prior microsecond-clock-keyed fallback could
    silently drop concurrent writes via INSERT OR IGNORE).
    """
    import hashlib
    if idempotency_id:
        seed = f"{channel}:{idempotency_id}".encode("utf-8")
        return f"atom-{channel}-" + hashlib.sha256(seed).hexdigest()[:20]
    # Non-idempotent path: ULID is already a project dependency.
    from ulid import ULID
    return f"atom-{channel}-{ULID()}"


def _find_by_idempotency(
    conn: sqlite3.Connection, channel: str, idempotency_id: str,
) -> str | None:
    """Look up an existing atom by (channel, idempotency_id).

    Uses SQLite's JSON1 ``json_extract`` for exact-match equality on the
    ``idempotency_id`` field embedded in ``scope_tags``. The earlier
    LIKE-based implementation treated ``_`` and ``%`` as wildcards,
    causing false-positive idempotency matches across unrelated keys
    (regression test: ``test_v0214_hardening.py::TestIdempotencyExactness``).

    Equality on ``json_extract`` is index-friendly when an expression
    index exists; without one, this is a sequential scan filtered by
    ``type``, identical in cost to the previous LIKE scan but correct.
    """
    row = conn.execute(
        "SELECT atom_id FROM atoms WHERE type = ? "
        "AND json_extract(scope_tags, '$.idempotency_id') = ? LIMIT 1",
        (channel, idempotency_id),
    ).fetchone()
    return row[0] if row else None


def _scope_tags_for_atom(
    conn: sqlite3.Connection, atom_id: str,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT scope_tags FROM atoms WHERE atom_id = ?", (atom_id,),
    ).fetchone()
    if row is None or not row[0]:
        return {}
    try:
        d = json.loads(row[0])
        return d if isinstance(d, dict) else {}
    except json.JSONDecodeError:
        return {}


def _safe_json(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    if isinstance(text, dict):
        return text
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


__all__ = [
    "AuthorityTier",
    "ChannelHit",
    "ChannelSpec",
    "MemoryChannel",
    "get_channel",
    "list_channels",
    "register_channel",
    "universal_recall",
]
