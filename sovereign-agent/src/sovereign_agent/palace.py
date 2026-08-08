"""
╔══════════════════════════════════════════════════════════════════════════╗
║  palace.py — Structured layer over atoms.db                              ║
║  v0.2.7 — Inspired by MemPalace (Milla Jovovich, @bensig).               ║
║  https://github.com/MemPalace/mempalace                                  ║
╚══════════════════════════════════════════════════════════════════════════╝

The atom store (``atoms.db``) is flat: each atom is a content blob plus
an embedding. Great for "things related to X" semantic search. Bad for
scale — at 10K+ atoms semantic search retrieves noise faster than signal.

The Palace adds two structured layers ON TOP of the atom store, both
persisted in a separate ``palace.db``:

  ◊ CLOSETS — short index documents that point to groups of related atoms.
    "topic | entities | →atom_id_1, atom_id_2, atom_id_3"
    Search the closets first (small, fast); then open referenced atoms.
    This is MemPalace's primary insight, adapted to atoms-as-leaves.

  ◊ TRIPLES — typed entity-relationship-entity facts with temporal
    validity. "(Max, child_of, Alice, valid_from='2015-04-01')". Subject,
    predicate, object — a tiny knowledge graph. Lets you ask "what was
    true about X on date D?" and "what supersedes Y?"

Both layers are PROJECTIONS over atoms — they can be dropped and rebuilt
from atoms.db without losing data. Atoms remain immutable ground truth.

Storage minimalism: this is one extra SQLite file (~1-5 MB for 1000s of
atoms). No ChromaDB, no sentence-transformers, no new heavyweight deps.
Embeddings continue to come from your Ollama-served nomic-embed-text.

What the Palace deliberately does NOT do (vs. MemPalace upstream):

  - No verbatim text storage at the closet layer. Atoms are already that.
  - No conversation-mining bias. The Palace is corpus-agnostic.
  - No external vector DB. SQLite + cosine in Python is enough at our scale.
  - No regex extractor for "decisions/preferences/milestones". Out of scope
    for v0.2.7; can be added later as a `palace-mine` planner.

Future v0.2.8+ candidates:

  - A ``palace`` planner that ingests atoms in batches and emits closets.
  - A ``sovereign palace query`` command for graph-walked retrieval.
  - BM25 hybrid search over closet text.
  - Episodic chains (atom → atom links forming a temporal narrative spine).
"""
from __future__ import annotations

import contextlib
import json
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


# ─── Schema ─────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,                -- e.g. 'room-genesis-seeds-research'
    name TEXT NOT NULL,                 -- human-readable label
    description TEXT NOT NULL DEFAULT '',
    schema_json TEXT NOT NULL DEFAULT '{}',  -- room schema (typed slot definitions)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS closets (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    entities TEXT NOT NULL DEFAULT '',  -- semicolon-separated for fast LIKE
    atom_ids TEXT NOT NULL,             -- comma-separated atom_ids in atoms.db
    embedding BLOB,                     -- json-encoded list[float] from nomic-embed-text
    source_file TEXT,                   -- file that produced this closet (for purges)
    created_at TEXT NOT NULL,
    FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_closets_room ON closets(room_id);
CREATE INDEX IF NOT EXISTS idx_closets_source_file ON closets(source_file);
CREATE INDEX IF NOT EXISTS idx_closets_topic ON closets(topic);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,                -- canonical form, e.g. 'entity-genesis-seeds'
    name TEXT NOT NULL,                 -- display name
    type TEXT NOT NULL DEFAULT 'unknown',
    properties_json TEXT NOT NULL DEFAULT '{}',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS triples (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT,                     -- nullable: literal-valued triples use object_literal
    object_literal TEXT,                -- when object is a value, not an entity
    valid_from TEXT,                    -- ISO date or RFC3339; null = always
    valid_to TEXT,                      -- null = still true
    confidence REAL NOT NULL DEFAULT 1.0,
    source_atom_ids TEXT NOT NULL DEFAULT '',  -- comma-separated atom_ids
    source_closet_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(subject_id) REFERENCES entities(id),
    FOREIGN KEY(object_id) REFERENCES entities(id)
);

CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject_id);
CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object_id);
CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
CREATE INDEX IF NOT EXISTS idx_triples_valid ON triples(valid_from, valid_to);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Dataclasses ────────────────────────────────────────────────────────────


@dataclass
class Room:
    """A themed container — research, code, transcripts, etc.

    Schema is opaque JSON: callers may put their own slot definitions there
    (the Palace doesn't enforce them; that's a v0.2.8 concern).
    """
    id: str
    name: str
    description: str = ""
    schema: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass
class Closet:
    """An index pointer that groups related atoms by topic.

    The ``embedding`` field is the topic line's embedding — used for
    semantic search over the closet layer itself. When None, the closet
    is keyword-only.
    """
    id: str
    room_id: str
    topic: str
    entities: list[str] = field(default_factory=list)
    atom_ids: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    source_file: str | None = None
    created_at: str = field(default_factory=_utc_now)


@dataclass
class Entity:
    """A named thing — person, project, concept, place."""
    id: str
    name: str
    type: str = "unknown"
    properties: dict = field(default_factory=dict)
    first_seen: str = field(default_factory=_utc_now)
    last_seen: str = field(default_factory=_utc_now)


@dataclass
class Triple:
    """A typed fact: subject → predicate → object, with optional temporal bounds.

    If ``object_id`` is set, the object is another entity (graph edge).
    If ``object_literal`` is set, the object is a string value (attribute).
    Exactly one of the two must be set.
    """
    id: str
    subject_id: str
    predicate: str
    object_id: str | None = None
    object_literal: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float = 1.0
    source_atom_ids: list[str] = field(default_factory=list)
    source_closet_id: str | None = None
    created_at: str = field(default_factory=_utc_now)


# ─── Errors ─────────────────────────────────────────────────────────────────


class PalaceError(Exception):
    """Base for palace operation errors."""


class RoomNotFound(PalaceError):
    pass


class TripleConstraintError(PalaceError):
    """Raised when a Triple has both object_id and object_literal, or neither."""


# ─── Storage class ──────────────────────────────────────────────────────────


class Palace:
    """SQLite-backed palace. Thread-safe via per-instance lock.

    Open via ``open_palace(db_path)``. Always close (or use context manager).
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection. Each call uses the same connection (WAL = safe).

        We hold ``self._lock`` for the duration of any single tx. Nested
        ``with palace._connect()`` would deadlock — by design; we don't nest.
        """
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path, isolation_level=None)
                self._conn.execute("PRAGMA busy_timeout = 5000")  # db-armor-d
                self._conn.execute("PRAGMA synchronous = NORMAL")
                self._conn.row_factory = sqlite3.Row
                self._conn.executescript(_SCHEMA_SQL)
            yield self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ── Rooms ────────────────────────────────────────────────────────────

    def create_room(
        self, *, room_id: str, name: str,
        description: str = "", schema: dict | None = None,
    ) -> Room:
        room = Room(
            id=room_id, name=name, description=description,
            schema=dict(schema or {}),
        )
        with self._connect() as c:
            c.execute(
                "INSERT INTO rooms(id, name, description, schema_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (room.id, room.name, room.description,
                 json.dumps(room.schema), room.created_at, room.updated_at),
            )
        return room

    def get_room(self, room_id: str) -> Room:
        with self._connect() as c:
            row = c.execute(
                "SELECT * FROM rooms WHERE id = ?", (room_id,)
            ).fetchone()
        if row is None:
            raise RoomNotFound(f"room {room_id!r} not found")
        return Room(
            id=row["id"], name=row["name"], description=row["description"],
            schema=json.loads(row["schema_json"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_rooms(self) -> list[Room]:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM rooms ORDER BY created_at").fetchall()
        return [
            Room(
                id=r["id"], name=r["name"], description=r["description"],
                schema=json.loads(r["schema_json"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ) for r in rows
        ]

    # ── Closets ──────────────────────────────────────────────────────────

    def add_closet(self, closet: Closet) -> Closet:
        with self._connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO closets"
                "(id, room_id, topic, entities, atom_ids, embedding, source_file, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    closet.id, closet.room_id, closet.topic,
                    ";".join(closet.entities), ",".join(closet.atom_ids),
                    json.dumps(closet.embedding) if closet.embedding else None,
                    closet.source_file, closet.created_at,
                ),
            )
        return closet

    def list_closets(self, *, room_id: str | None = None) -> list[Closet]:
        sql = "SELECT * FROM closets"
        params: tuple = ()
        if room_id:
            sql += " WHERE room_id = ?"
            params = (room_id,)
        sql += " ORDER BY created_at DESC"
        with self._connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_closet(r) for r in rows]

    def purge_closets_for_file(self, source_file: str) -> int:
        """Delete every closet generated from this source file. Returns count.

        Used when re-mining a file: drop stale closets, then re-emit fresh
        ones from current content. Same pattern as MemPalace upstream.
        """
        with self._connect() as c:
            cur = c.execute(
                "DELETE FROM closets WHERE source_file = ?", (source_file,)
            )
            return cur.rowcount

    def search_closets_keyword(
        self, query: str, *, limit: int = 10, room_id: str | None = None,
    ) -> list[Closet]:
        """Substring search over closet topic + entities. Cheap, no embedding.

        For semantic search use ``search_closets_semantic`` (requires the
        query to come pre-embedded — caller invokes embed_query tool).
        """
        like = f"%{query.lower()}%"
        sql = ("SELECT * FROM closets WHERE "
               "(LOWER(topic) LIKE ? OR LOWER(entities) LIKE ?)")
        params: list = [like, like]
        if room_id:
            sql += " AND room_id = ?"
            params.append(room_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_closet(r) for r in rows]

    def search_closets_semantic(
        self, query_embedding: list[float], *,
        limit: int = 10, room_id: str | None = None,
    ) -> list[tuple[Closet, float]]:
        """Cosine similarity over closet embeddings. Returns (closet, score)
        tuples, score in [-1, 1] where higher is more similar.

        At our scale (~thousands of closets) a Python cosine loop is fine.
        If the corpus grows past 100K closets, swap in faiss or sqlite-vec.
        """
        sql = "SELECT * FROM closets WHERE embedding IS NOT NULL"
        params: list = []
        if room_id:
            sql += " AND room_id = ?"
            params.append(room_id)
        with self._connect() as c:
            rows = c.execute(sql, params).fetchall()

        scored: list[tuple[Closet, float]] = []
        q_norm = _norm(query_embedding)
        if q_norm == 0:
            return []
        for row in rows:
            emb_json = row["embedding"]
            if not emb_json:
                continue
            try:
                emb = json.loads(emb_json)
            except json.JSONDecodeError:
                continue
            score = _cosine(query_embedding, emb, q_norm=q_norm)
            scored.append((_row_to_closet(row), score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:limit]

    # ── Entities ─────────────────────────────────────────────────────────

    def upsert_entity(self, entity: Entity) -> Entity:
        with self._connect() as c:
            existing = c.execute(
                "SELECT first_seen FROM entities WHERE id = ?", (entity.id,)
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE entities SET name = ?, type = ?, properties_json = ?, "
                    "last_seen = ? WHERE id = ?",
                    (entity.name, entity.type,
                     json.dumps(entity.properties), entity.last_seen, entity.id),
                )
            else:
                c.execute(
                    "INSERT INTO entities(id, name, type, properties_json, "
                    "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                    (entity.id, entity.name, entity.type,
                     json.dumps(entity.properties),
                     entity.first_seen, entity.last_seen),
                )
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
        if not row:
            return None
        return Entity(
            id=row["id"], name=row["name"], type=row["type"],
            properties=json.loads(row["properties_json"]),
            first_seen=row["first_seen"], last_seen=row["last_seen"],
        )

    # ── Triples ──────────────────────────────────────────────────────────

    def add_triple(self, triple: Triple) -> Triple:
        if (triple.object_id is None) == (triple.object_literal is None):
            raise TripleConstraintError(
                "Triple must have exactly one of object_id or object_literal"
            )
        with self._connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO triples"
                "(id, subject_id, predicate, object_id, object_literal, "
                " valid_from, valid_to, confidence, source_atom_ids, "
                " source_closet_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    triple.id, triple.subject_id, triple.predicate,
                    triple.object_id, triple.object_literal,
                    triple.valid_from, triple.valid_to, triple.confidence,
                    ",".join(triple.source_atom_ids), triple.source_closet_id,
                    triple.created_at,
                ),
            )
        return triple

    def query_subject(
        self, subject_id: str, *, as_of: str | None = None,
    ) -> list[Triple]:
        """All triples about this subject. Optional point-in-time filter.

        ``as_of`` is matched against ``valid_from <= as_of < valid_to`` —
        a triple with no bounds is always-true.
        """
        sql = "SELECT * FROM triples WHERE subject_id = ?"
        params: list = [subject_id]
        if as_of:
            sql += (
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to > ?)"
            )
            params.extend([as_of, as_of])
        sql += " ORDER BY created_at DESC"
        with self._connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_triple(r) for r in rows]

    def query_object(
        self, object_id: str, *, as_of: str | None = None,
    ) -> list[Triple]:
        sql = "SELECT * FROM triples WHERE object_id = ?"
        params: list = [object_id]
        if as_of:
            sql += (
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to > ?)"
            )
            params.extend([as_of, as_of])
        sql += " ORDER BY created_at DESC"
        with self._connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_triple(r) for r in rows]

    def invalidate_triple(self, triple_id: str, *, ended: str) -> bool:
        """Mark a triple as no-longer-true as of date ``ended``. True if updated."""
        with self._connect() as c:
            cur = c.execute(
                "UPDATE triples SET valid_to = ? WHERE id = ? AND valid_to IS NULL",
                (ended, triple_id),
            )
            return cur.rowcount > 0

    # ── Stats ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Counts for observability/reporting. v0.2.7+."""
        with self._connect() as c:
            return {
                "rooms": c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0],
                "closets": c.execute("SELECT COUNT(*) FROM closets").fetchone()[0],
                "entities": c.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                "triples": c.execute("SELECT COUNT(*) FROM triples").fetchone()[0],
                "active_triples": c.execute(
                    "SELECT COUNT(*) FROM triples WHERE valid_to IS NULL"
                ).fetchone()[0],
            }


# ─── Row helpers ────────────────────────────────────────────────────────────


def _row_to_closet(row: sqlite3.Row) -> Closet:
    emb = None
    if row["embedding"]:
        try:
            emb = json.loads(row["embedding"])
        except json.JSONDecodeError:
            emb = None
    return Closet(
        id=row["id"], room_id=row["room_id"], topic=row["topic"],
        entities=[e for e in (row["entities"] or "").split(";") if e],
        atom_ids=[a for a in (row["atom_ids"] or "").split(",") if a],
        embedding=emb, source_file=row["source_file"],
        created_at=row["created_at"],
    )


def _row_to_triple(row: sqlite3.Row) -> Triple:
    return Triple(
        id=row["id"],
        subject_id=row["subject_id"],
        predicate=row["predicate"],
        object_id=row["object_id"],
        object_literal=row["object_literal"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        confidence=row["confidence"],
        source_atom_ids=[a for a in (row["source_atom_ids"] or "").split(",") if a],
        source_closet_id=row["source_closet_id"],
        created_at=row["created_at"],
    )


# ─── Cosine similarity (Python; fine at our scale) ──────────────────────────


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine(a: list[float], b: list[float], *, q_norm: float | None = None) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    a_n = q_norm if q_norm is not None else _norm(a)
    b_n = _norm(b)
    if a_n == 0 or b_n == 0:
        return 0.0
    return dot / (a_n * b_n)


# ─── Open helper ────────────────────────────────────────────────────────────


def open_palace(db_path: Path | str | None = None) -> Palace:
    """Open the palace at the configured location (or override).

    Default location: ``<data_dir>/palace.db`` per ``Paths.palace_db``.
    """
    if db_path is None:
        from .config import SETTINGS
        db_path = SETTINGS.paths.palace_db
    return Palace(Path(db_path))
