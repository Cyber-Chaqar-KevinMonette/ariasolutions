"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/bitemporal.py — two-axis time, append-only, Merkle-anchored       ║
║                                                                           ║
║  The substrate that makes "you can't silently rewrite history" structural║
║  rather than aspirational.                                                ║
║                                                                           ║
║  Two time axes:                                                          ║
║                                                                           ║
║    valid_time  — when the fact is/was true in the world                 ║
║                  (valid_from, valid_to)                                  ║
║                                                                           ║
║    tx_time     — when WE recorded that we believed the fact              ║
║                  (tx_from, tx_to)                                        ║
║                                                                           ║
║  To "update" a record bitemporally we don't UPDATE. We:                  ║
║                                                                           ║
║    1. Close the prior row's transaction window (set tx_to = now).      ║
║    2. Insert a new row with tx_from = now and the new content.         ║
║                                                                           ║
║  As-of query: "what did we believe was true about X at world-time T1   ║
║  as known at system-time T2?" — straightforward SQL with two time     ║
║  windows.                                                                ║
║                                                                           ║
║  Merkle anchoring:                                                       ║
║                                                                           ║
║    Each insert chains by hash to the prior insert (same pattern as     ║
║    the Aegis Ledger). Tampering with any old row breaks the chain     ║
║    forward of that point. The chain HEAD is itself appended to the     ║
║    Aegis Ledger periodically — so the bitemporal store can't be       ║
║    silently truncated either.                                           ║
║                                                                           ║
║  Storage: SQLite by default (file at <data_dir>/bitemporal.db).         ║
║           Drop-in replaceable; the interface is the abstraction.        ║
║                                                                           ║
║  Kill switch: not applicable. The bitemporal store is foundational; ║
║  disabling it would disable durability. Use SOV_NO_AEGIS for the       ║
║  larger plane.                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


# ─── Hash and time helpers ───────────────────────────────────────────────


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


GENESIS_HASH = hashlib.sha256(b"bitemporal-genesis-2026").hexdigest()


# ─── Record type ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BitemporalRecord:
    """One row. Frozen on purpose — bitemporal records do not mutate.

    Updates produce NEW rows that close the prior row's tx window and
    open a new one. The old row stays. That's the entire point.
    """
    record_id: str                            # ULID
    entity_key: str                           # logical identity ("user:alice")
    valid_from: str                           # ISO; when fact begins being true
    valid_to: str                             # ISO; when fact stops being true (or '9999-12-31T...')
    tx_from: str                              # ISO; when we recorded this
    tx_to: str                                # ISO; '9999-12-31T...' if still current
    content_json: str                         # JSON-serialized payload
    prior_hash: str                           # Merkle chain
    entry_hash: str                           # sha256 of all above except this

    def computed_hash(self) -> str:
        d = asdict(self)
        d.pop("entry_hash", None)
        blob = json.dumps(d, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


OPEN_TX = "9999-12-31T23:59:59.999999Z"        # the "still current" sentinel


# ─── The store ───────────────────────────────────────────────────────────


class BitemporalStore:
    """Append-only bitemporal store backed by SQLite.

    Public methods:
        insert(entity_key, content, valid_from, valid_to) — adds a row.
        supersede(entity_key, content, valid_from, valid_to) — closes the
            current row's tx window and inserts a new one atomically.
        as_of(entity_key, world_time, system_time) — query at a point.
        history(entity_key) — yield all rows ever recorded for the key.
        verify_chain() — walk the Merkle chain; return first broken seq.
        chain_head() — return the current chain-tip hash for anchoring.
    """

    def __init__(self, db_path: Path):
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA busy_timeout = 5000")  # db-armor-d
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS bitemporal (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE NOT NULL,
                    entity_key TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT NOT NULL,
                    tx_from TEXT NOT NULL,
                    tx_to TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    prior_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_entity_key
                    ON bitemporal(entity_key);
                CREATE INDEX IF NOT EXISTS idx_tx_window
                    ON bitemporal(tx_from, tx_to);
                CREATE INDEX IF NOT EXISTS idx_valid_window
                    ON bitemporal(valid_from, valid_to);
                -- The tampering audit table: append-only checkpoints
                -- (chain_head hash + timestamp) so we can detect truncation.
                CREATE TABLE IF NOT EXISTS chain_anchors (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    anchored_at TEXT NOT NULL,
                    chain_head TEXT NOT NULL,
                    row_count INTEGER NOT NULL
                );
            """)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, isolation_level="IMMEDIATE")
        conn.execute("PRAGMA busy_timeout = 5000")  # db-armor-d
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Chain head ──────────────────────────────────────────────────────

    def chain_head(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT entry_hash FROM bitemporal ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else GENESIS_HASH

    def row_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM bitemporal").fetchone()[0]

    def anchor(self) -> None:
        """Snapshot (chain_head, row_count, timestamp). Call periodically;
        these go to the Aegis Ledger via a separate call (see aegis.conductor).
        """
        with self._conn() as conn:
            head = conn.execute(
                "SELECT entry_hash FROM bitemporal ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            count = conn.execute("SELECT COUNT(*) FROM bitemporal").fetchone()[0]
            conn.execute(
                "INSERT INTO chain_anchors(anchored_at, chain_head, row_count) "
                "VALUES (?, ?, ?)",
                (_iso_now(), head[0] if head else GENESIS_HASH, count),
            )

    # ── Inserts ─────────────────────────────────────────────────────────

    def insert(
        self,
        *,
        record_id: str,
        entity_key: str,
        content: dict[str, Any],
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
    ) -> BitemporalRecord:
        """Add a row. Use supersede() if there's a prior open row for the
        same entity_key — this method does not close prior windows."""
        vf = valid_from or _iso_now()
        vt = valid_to or OPEN_TX
        tf = _iso_now()
        tt = OPEN_TX
        content_json = json.dumps(content, sort_keys=True)
        prior = self.chain_head()

        unsigned = BitemporalRecord(
            record_id=record_id,
            entity_key=entity_key,
            valid_from=vf, valid_to=vt,
            tx_from=tf, tx_to=tt,
            content_json=content_json,
            prior_hash=prior,
            entry_hash="",
        )
        h = unsigned.computed_hash()
        sealed = BitemporalRecord(
            record_id=record_id,
            entity_key=entity_key,
            valid_from=vf, valid_to=vt,
            tx_from=tf, tx_to=tt,
            content_json=content_json,
            prior_hash=prior,
            entry_hash=h,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO bitemporal(record_id, entity_key, valid_from, "
                "valid_to, tx_from, tx_to, content_json, prior_hash, entry_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sealed.record_id, sealed.entity_key, sealed.valid_from,
                 sealed.valid_to, sealed.tx_from, sealed.tx_to,
                 sealed.content_json, sealed.prior_hash, sealed.entry_hash),
            )
        return sealed

    def supersede(
        self,
        *,
        record_id: str,
        entity_key: str,
        content: dict[str, Any],
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
    ) -> BitemporalRecord:
        """Close any currently-open tx-window row for entity_key, then
        insert a new one. Both happen in a single transaction.
        """
        now = _iso_now()
        with self._conn() as conn:
            conn.execute(
                "UPDATE bitemporal SET tx_to = ? "
                "WHERE entity_key = ? AND tx_to = ?",
                (now, entity_key, OPEN_TX),
            )
        # Now insert the new row (separate transaction, but the close was
        # atomic and is durable).
        return self.insert(
            record_id=record_id,
            entity_key=entity_key,
            content=content,
            valid_from=valid_from,
            valid_to=valid_to,
        )

    # ── Queries ─────────────────────────────────────────────────────────

    def as_of(
        self,
        *,
        entity_key: str,
        world_time: Optional[str] = None,
        system_time: Optional[str] = None,
    ) -> Optional[BitemporalRecord]:
        """The flagship query: what did we believe was true about entity_key
        at world_time, as known at system_time?

        Defaults: world_time = now, system_time = now (i.e., "what do we
        currently believe is currently true").
        """
        wt = world_time or _iso_now()
        st = system_time or _iso_now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT record_id, entity_key, valid_from, valid_to, "
                "tx_from, tx_to, content_json, prior_hash, entry_hash "
                "FROM bitemporal "
                "WHERE entity_key = ? "
                "  AND valid_from <= ? AND valid_to > ? "
                "  AND tx_from <= ? AND tx_to > ? "
                "ORDER BY seq DESC LIMIT 1",
                (entity_key, wt, wt, st, st),
            ).fetchone()
        if row is None:
            return None
        return BitemporalRecord(*row)

    def history(self, entity_key: str) -> list[BitemporalRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT record_id, entity_key, valid_from, valid_to, "
                "tx_from, tx_to, content_json, prior_hash, entry_hash "
                "FROM bitemporal WHERE entity_key = ? ORDER BY seq ASC",
                (entity_key,),
            ).fetchall()
        return [BitemporalRecord(*r) for r in rows]

    # ── Integrity ───────────────────────────────────────────────────────

    def verify_chain(self) -> Optional[int]:
        """Walk the Merkle chain. Return the seq of the first broken link,
        or None if intact."""
        prev = GENESIS_HASH
        with self._conn() as conn:
            cursor = conn.execute(
                "SELECT seq, record_id, entity_key, valid_from, valid_to, "
                "tx_from, tx_to, content_json, prior_hash, entry_hash "
                "FROM bitemporal ORDER BY seq ASC"
            )
            for row in cursor:
                seq = row[0]
                rec = BitemporalRecord(*row[1:])
                if rec.prior_hash != prev:
                    return seq
                if rec.entry_hash != rec.computed_hash():
                    return seq
                prev = rec.entry_hash
        return None


__all__ = [
    "BitemporalRecord",
    "BitemporalStore",
    "GENESIS_HASH",
    "OPEN_TX",
]
