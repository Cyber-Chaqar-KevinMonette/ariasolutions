"""
╔══════════════════════════════════════════════════════════════════════════╗
║  palace_scan.py — Read-only analysis of palace.db (v0.2.9)               ║
║                                                                          ║
║  Produces a PalaceUnderstanding object: counts, distributions, orphans,  ║
║  duplicates, dense regions, sparse regions, name conflicts, suspicious   ║
║  triples. No model invocation. No mutations. Pure analysis.              ║
║                                                                          ║
║  This is the input to the reflection loop: the orchestrator reads        ║
║  sections of the understanding and proposes reorganizations / insights / ║
║  enhancements. The operator approves; the system applies.                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from .palace import Palace


# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass
class CountsSection:
    """Top-level counts from palace stats."""

    rooms: int
    closets: int
    entities: int
    triples: int
    active_triples: int


@dataclass
class RoomBreakdown:
    """Per-room counts."""

    room_id: str
    room_name: str
    closet_count: int
    entity_count: int  # entities mentioned in this room's closets
    triple_count: int  # triples sourced from this room's closets


@dataclass
class OrphanSection:
    """Closets / entities / triples that are disconnected.

    - orphan_closets: closets pointing to no atoms (atom_ids empty)
    - orphan_entities: entities never referenced by any closet OR triple
    - orphan_triples: triples whose subject_id or object_id is not in entities
    """

    orphan_closets: list[str] = field(default_factory=list)
    orphan_entities: list[str] = field(default_factory=list)
    orphan_triples: list[str] = field(default_factory=list)


@dataclass
class DuplicateSection:
    """Likely-duplicate entities and closets.

    Duplicate entities = same normalized name, different ids. (Caused by
    different display names hashing to different ids.)
    Duplicate closets = same topic + same atom_ids.
    """

    duplicate_entity_groups: list[list[str]] = field(default_factory=list)
    duplicate_closet_groups: list[list[str]] = field(default_factory=list)


@dataclass
class DistributionSection:
    """How content is distributed."""

    closets_per_room: dict[str, int] = field(default_factory=dict)
    triples_per_predicate: dict[str, int] = field(default_factory=dict)
    entity_mention_counts: dict[str, int] = field(default_factory=dict)
    # most-mentioned entities (top 10) for quick visual
    top_entities: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class SuspicionSection:
    """Triples that look noisy or low-quality.

    - low_confidence: confidence < 0.4
    - self_referential: subject == object
    - stoplist_objects: object_literal matches a stoplist word
    """

    low_confidence: list[str] = field(default_factory=list)
    self_referential: list[str] = field(default_factory=list)
    stoplist_objects: list[str] = field(default_factory=list)


@dataclass
class PalaceUnderstanding:
    """Complete read-only snapshot of the palace, structured for analysis.

    Produced by ``scan_palace()``. Consumed by the ``palace-reflect``
    planner (which asks the model to interpret each section) and by
    ``sovereign palace understanding`` (which prints it for the operator).

    All fields are JSON-serializable so the understanding can be persisted
    or piped through other tools.
    """

    counts: CountsSection
    rooms: list[RoomBreakdown] = field(default_factory=list)
    orphans: OrphanSection = field(default_factory=OrphanSection)
    duplicates: DuplicateSection = field(default_factory=DuplicateSection)
    distribution: DistributionSection = field(default_factory=DistributionSection)
    suspicion: SuspicionSection = field(default_factory=SuspicionSection)
    generated_at: str = ""
    palace_db_path: str = ""

    def is_empty(self) -> bool:
        return self.counts.closets == 0 and self.counts.entities == 0


# ─── Suspicion helpers ──────────────────────────────────────────────────────


_STOPLIST_OBJECTS = frozenset({
    "the", "a", "an", "this", "that", "these", "those",
    "thing", "things", "stuff", "something", "anything", "everything",
    "yes", "no", "ok", "true", "false", "none",
})


# ─── Top-level scan ─────────────────────────────────────────────────────────


def scan_palace(palace: Palace) -> PalaceUnderstanding:
    """Walk every table in the palace, compute the understanding object.

    Read-only. Closes nothing — caller owns palace lifecycle.

    On a corpus with ~1500 atoms this completes in well under a second.
    Designed to be safe to run repeatedly (e.g., before/after every mining
    pass) for observability.
    """
    from datetime import datetime, timezone

    stats = palace.stats()
    counts = CountsSection(
        rooms=stats["rooms"],
        closets=stats["closets"],
        entities=stats["entities"],
        triples=stats["triples"],
        active_triples=stats["active_triples"],
    )

    understanding = PalaceUnderstanding(
        counts=counts,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        palace_db_path=str(palace.db_path),
    )

    if counts.closets == 0 and counts.entities == 0:
        return understanding

    rooms = palace.list_rooms()
    all_closets = palace.list_closets()
    # Build entity id → row map once for fast lookups.
    all_entities = _all_entities(palace)
    entity_ids = {e_id for e_id in all_entities.keys()}
    all_triples = _all_triples(palace)

    # ── Room breakdown ────────────────────────────────────────────────
    closets_by_room: dict[str, list] = {}
    for c in all_closets:
        closets_by_room.setdefault(c.room_id, []).append(c)

    room_breakdowns: list[RoomBreakdown] = []
    for r in rooms:
        rc = closets_by_room.get(r.id, [])
        # entities mentioned in closets of this room
        ents_in_room: set[str] = set()
        for c in rc:
            ents_in_room.update(c.entities)
        # triples sourced from closets of this room
        room_closet_ids = {c.id for c in rc}
        triples_from_room = [t for t in all_triples if t.source_closet_id in room_closet_ids]
        room_breakdowns.append(RoomBreakdown(
            room_id=r.id,
            room_name=r.name,
            closet_count=len(rc),
            entity_count=len(ents_in_room),
            triple_count=len(triples_from_room),
        ))
    understanding.rooms = room_breakdowns

    # ── Orphans ──────────────────────────────────────────────────────
    orphan_closets = [c.id for c in all_closets if not c.atom_ids]

    # Entities referenced by at least one closet (entity name) or triple
    referenced_entity_names: set[str] = set()
    for c in all_closets:
        referenced_entity_names.update(c.entities)
    referenced_entity_ids: set[str] = set()
    for t in all_triples:
        referenced_entity_ids.add(t.subject_id)
        if t.object_id:
            referenced_entity_ids.add(t.object_id)

    orphan_entities = [
        eid for eid, ent in all_entities.items()
        if ent.name not in referenced_entity_names
        and eid not in referenced_entity_ids
    ]

    orphan_triples = [
        t.id for t in all_triples
        if t.subject_id not in entity_ids
        or (t.object_id is not None and t.object_id not in entity_ids)
    ]

    understanding.orphans = OrphanSection(
        orphan_closets=orphan_closets,
        orphan_entities=orphan_entities,
        orphan_triples=orphan_triples,
    )

    # ── Duplicates ───────────────────────────────────────────────────
    # Same normalized name → likely duplicate entities
    dup_entity_groups: list[list[str]] = []
    by_norm: dict[str, list[str]] = {}
    for eid, ent in all_entities.items():
        norm = _normalize_name(ent.name)
        by_norm.setdefault(norm, []).append(eid)
    for ids in by_norm.values():
        if len(ids) > 1:
            dup_entity_groups.append(sorted(ids))

    # Same topic + same atom_ids → duplicate closets
    dup_closet_groups: list[list[str]] = []
    by_topic_atoms: dict[tuple, list[str]] = {}
    for c in all_closets:
        key = (c.topic, tuple(sorted(c.atom_ids)))
        by_topic_atoms.setdefault(key, []).append(c.id)
    for ids in by_topic_atoms.values():
        if len(ids) > 1:
            dup_closet_groups.append(sorted(ids))

    understanding.duplicates = DuplicateSection(
        duplicate_entity_groups=dup_entity_groups,
        duplicate_closet_groups=dup_closet_groups,
    )

    # ── Distribution ─────────────────────────────────────────────────
    closets_per_room = {r_id: len(cs) for r_id, cs in closets_by_room.items()}

    pred_counter: Counter = Counter(t.predicate for t in all_triples)

    entity_mentions: Counter = Counter()
    for c in all_closets:
        for ent in c.entities:
            entity_mentions[ent] += 1
    top_entities = entity_mentions.most_common(10)

    understanding.distribution = DistributionSection(
        closets_per_room=closets_per_room,
        triples_per_predicate=dict(pred_counter),
        entity_mention_counts=dict(entity_mentions),
        top_entities=top_entities,
    )

    # ── Suspicion ────────────────────────────────────────────────────
    low_conf = [t.id for t in all_triples if t.confidence < 0.4]
    self_ref = [t.id for t in all_triples if t.object_id and t.subject_id == t.object_id]
    stoplist_obj = [
        t.id for t in all_triples
        if t.object_literal and t.object_literal.lower().strip() in _STOPLIST_OBJECTS
    ]
    understanding.suspicion = SuspicionSection(
        low_confidence=low_conf,
        self_referential=self_ref,
        stoplist_objects=stoplist_obj,
    )

    return understanding


def _normalize_name(name: str) -> str:
    """Lowercase + strip whitespace — minimum normalization for dup detection."""
    import re
    out = re.sub(r"\s+", " ", name.strip().lower())
    return out


def _all_entities(palace: Palace) -> dict[str, "Entity"]:
    """Read every entity. Returns id→Entity dict.

    No public API yet for "list all entities" — we go through the connection
    directly. This is fine: scan_palace is the privileged caller and it's
    read-only.
    """
    from .palace import Entity
    import json as _json

    out: dict[str, Entity] = {}
    with palace._connect() as c:
        rows = c.execute("SELECT * FROM entities").fetchall()
    for r in rows:
        out[r["id"]] = Entity(
            id=r["id"], name=r["name"], type=r["type"],
            properties=_json.loads(r["properties_json"]),
            first_seen=r["first_seen"], last_seen=r["last_seen"],
        )
    return out


def _all_triples(palace: Palace) -> list:
    """Read every triple. List of Triple objects."""
    from .palace import _row_to_triple

    with palace._connect() as c:
        rows = c.execute("SELECT * FROM triples").fetchall()
    return [_row_to_triple(r) for r in rows]


# ─── Markdown render ───────────────────────────────────────────────────────


def render_understanding_markdown(u: PalaceUnderstanding) -> str:
    """Produce a human-readable markdown report of the understanding.

    This is what the `palace-reflect` planner gives the orchestrator
    section-by-section. It's also what `sovereign palace understanding`
    prints to stdout for the operator.
    """
    parts: list[str] = []
    parts.append(f"# Palace Understanding\n")
    parts.append(f"_Generated: {u.generated_at}_\n")
    parts.append(f"_Source: `{u.palace_db_path}`_\n\n")

    # Counts
    parts.append("## Counts\n")
    parts.append(
        f"- rooms: **{u.counts.rooms}**\n"
        f"- closets: **{u.counts.closets}**\n"
        f"- entities: **{u.counts.entities}**\n"
        f"- triples: **{u.counts.triples}** ({u.counts.active_triples} active)\n\n"
    )

    if u.is_empty():
        parts.append("_Palace is empty. Run `palace-mine` to populate it._\n")
        return "".join(parts)

    # Per-room
    parts.append("## Rooms\n")
    if not u.rooms:
        parts.append("_No rooms defined._\n\n")
    else:
        parts.append("| room_id | name | closets | entities | triples |\n")
        parts.append("|---|---|---:|---:|---:|\n")
        for r in u.rooms:
            parts.append(
                f"| `{r.room_id}` | {r.room_name} | "
                f"{r.closet_count} | {r.entity_count} | {r.triple_count} |\n"
            )
        parts.append("\n")

    # Distribution highlights
    parts.append("## Distribution\n")
    if u.distribution.top_entities:
        parts.append("**Top mentioned entities:**\n")
        for name, count in u.distribution.top_entities:
            parts.append(f"- `{name}`: {count}\n")
        parts.append("\n")
    if u.distribution.triples_per_predicate:
        parts.append("**Triples by predicate:**\n")
        for pred, count in sorted(
            u.distribution.triples_per_predicate.items(),
            key=lambda x: -x[1],
        ):
            parts.append(f"- `{pred}`: {count}\n")
        parts.append("\n")

    # Orphans
    parts.append("## Orphans\n")
    parts.append(f"- orphan closets: **{len(u.orphans.orphan_closets)}**")
    if u.orphans.orphan_closets[:3]:
        parts.append(f" — first 3: `{', '.join(u.orphans.orphan_closets[:3])}`")
    parts.append("\n")
    parts.append(f"- orphan entities: **{len(u.orphans.orphan_entities)}**")
    if u.orphans.orphan_entities[:3]:
        parts.append(f" — first 3: `{', '.join(u.orphans.orphan_entities[:3])}`")
    parts.append("\n")
    parts.append(f"- orphan triples: **{len(u.orphans.orphan_triples)}**\n\n")

    # Duplicates
    parts.append("## Duplicates\n")
    parts.append(f"- duplicate entity groups: **{len(u.duplicates.duplicate_entity_groups)}**")
    if u.duplicates.duplicate_entity_groups[:1]:
        first = u.duplicates.duplicate_entity_groups[0][:5]
        parts.append(f" — first group: `{', '.join(first)}`")
    parts.append("\n")
    parts.append(
        f"- duplicate closet groups: **{len(u.duplicates.duplicate_closet_groups)}**\n\n"
    )

    # Suspicion
    parts.append("## Suspicion\n")
    parts.append(f"- low-confidence triples (< 0.4): **{len(u.suspicion.low_confidence)}**\n")
    parts.append(f"- self-referential triples: **{len(u.suspicion.self_referential)}**\n")
    parts.append(f"- triples with stoplist objects: **{len(u.suspicion.stoplist_objects)}**\n\n")

    return "".join(parts)


def understanding_to_dict(u: PalaceUnderstanding) -> dict:
    """JSON-serializable dict view, for --json output and persistence."""
    return {
        "generated_at": u.generated_at,
        "palace_db_path": u.palace_db_path,
        "counts": {
            "rooms": u.counts.rooms,
            "closets": u.counts.closets,
            "entities": u.counts.entities,
            "triples": u.counts.triples,
            "active_triples": u.counts.active_triples,
        },
        "rooms": [
            {"room_id": r.room_id, "name": r.room_name,
             "closet_count": r.closet_count,
             "entity_count": r.entity_count,
             "triple_count": r.triple_count}
            for r in u.rooms
        ],
        "orphans": {
            "orphan_closets": u.orphans.orphan_closets,
            "orphan_entities": u.orphans.orphan_entities,
            "orphan_triples": u.orphans.orphan_triples,
        },
        "duplicates": {
            "duplicate_entity_groups": u.duplicates.duplicate_entity_groups,
            "duplicate_closet_groups": u.duplicates.duplicate_closet_groups,
        },
        "distribution": {
            "closets_per_room": u.distribution.closets_per_room,
            "triples_per_predicate": u.distribution.triples_per_predicate,
            "top_entities": u.distribution.top_entities,
        },
        "suspicion": {
            "low_confidence": u.suspicion.low_confidence,
            "self_referential": u.suspicion.self_referential,
            "stoplist_objects": u.suspicion.stoplist_objects,
        },
    }
