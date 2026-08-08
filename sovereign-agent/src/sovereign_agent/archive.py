"""
╔══════════════════════════════════════════════════════════════════════════╗
║  archive.py — content-addressed durable blob store                       ║
║  v0.2.18.0                                                                ║
║                                                                           ║
║  Inspired by Git's object store, IPFS, and Datomic. Every piece of      ║
║  content Aria stores can be hashed; the hash IS the canonical id.       ║
║  Two atoms with the same body share one archive row.                    ║
║                                                                           ║
║  WHY                                                                     ║
║                                                                           ║
║    * Deduplication: a recall that quotes an atom doesn't duplicate     ║
║      the content. Same hash, same row.                                  ║
║    * Verifiability: the operator can re-hash any blob and prove it     ║
║      hasn't been tampered with.                                         ║
║    * Replication: a remote backup is "the set of (hash, content)        ║
║      pairs I don't have yet" — trivially incremental.                  ║
║    * Signing: optional detached signature column lets the operator     ║
║      cryptographically commit to a snapshot of important content.      ║
║                                                                           ║
║  RELATIONSHIP TO ATOMS                                                  ║
║                                                                           ║
║    Atoms are the *event* layer (when, by whom, with what claims).     ║
║    Archive is the *content* layer (what bytes, with what hash).        ║
║    An atom's ``content_ref`` can be a SHA-256 hash pointing into the   ║
║    archive. This is additive — atoms that have inline content keep    ║
║    working unchanged. Channels that opt in get dedup for free.        ║
║                                                                           ║
║  SEALING                                                                ║
║                                                                           ║
║    A sealed archive row cannot be deleted, ever — even if its refcount  ║
║    drops to zero. This is the audit-grade option: once Aria says       ║
║    "this content is forever," she means it.                            ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ArchiveEntry:
    content_hash: str
    size_bytes: int
    content_type: str
    encoding: str
    created_at: str
    refcount: int
    sealed: bool
    signature: str | None = None


@dataclass(frozen=True)
class ArchiveStats:
    total_objects: int
    total_bytes: int
    sealed_objects: int
    unique_content_types: int
    avg_refcount: float


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_archive_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent / "sql" / "014_archive.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent / "sql" / "014_archive.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"014_archive.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


class ContentArchive:
    """Content-addressed store. Atoms and other channels can point here."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        ensure_archive_schema(conn)

    @contextmanager
    def _writer_tx(self) -> Iterator[None]:
        in_tx = self.conn.in_transaction
        if not in_tx:
            self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            if not in_tx:
                self.conn.commit()
        except Exception:
            if not in_tx:
                self.conn.rollback()
            raise

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _ref_id(content_hash: str, ref_kind: str, ref_id: str) -> str:
        seed = f"{content_hash}::{ref_kind}::{ref_id}"
        return "ar-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    # ── Put ──────────────────────────────────────────────────────────

    def put(
        self,
        content: bytes | str,
        *,
        content_type: str = "text/plain",
        encoding: str = "utf-8",
        ref_kind: str | None = None,
        ref_id: str | None = None,
    ) -> str:
        """Store content. Returns the SHA-256 hex hash.

        If the content already exists, returns the existing hash and
        increments the refcount (if ref_kind+ref_id given). Idempotent
        per (content, ref_kind, ref_id) tuple — re-referencing from
        the same source doesn't double-count.
        """
        if isinstance(content, str):
            data = content.encode(encoding)
        else:
            data = bytes(content)
        chash = sha256_hex(data)
        now = self._now()

        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT content_hash FROM archive WHERE content_hash = ?",
                (chash,),
            ).fetchone()
            if not existing:
                self.conn.execute(
                    "INSERT INTO archive (content_hash, size_bytes, content_type, "
                    "content, encoding, created_at, refcount, sealed) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
                    (chash, len(data), content_type, data, encoding, now),
                )

            if ref_kind and ref_id:
                rid = self._ref_id(chash, ref_kind, ref_id)
                ref_existing = self.conn.execute(
                    "SELECT removed_at FROM archive_refs WHERE ref_id = ?",
                    (rid,),
                ).fetchone()
                if ref_existing is None:
                    self.conn.execute(
                        "INSERT INTO archive_refs (ref_id, content_hash, "
                        "ref_kind, ref_id_value, added_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (rid, chash, ref_kind, ref_id, now),
                    )
                    self.conn.execute(
                        "UPDATE archive SET refcount = refcount + 1 "
                        "WHERE content_hash = ?",
                        (chash,),
                    )
                elif ref_existing[0] is not None:
                    # Was removed; restore
                    self.conn.execute(
                        "UPDATE archive_refs SET removed_at = NULL WHERE ref_id = ?",
                        (rid,),
                    )
                    self.conn.execute(
                        "UPDATE archive SET refcount = refcount + 1 "
                        "WHERE content_hash = ?",
                        (chash,),
                    )
        return chash

    # ── Get ──────────────────────────────────────────────────────────

    def get(self, content_hash: str) -> bytes | None:
        row = self.conn.execute(
            "SELECT content FROM archive WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        return row[0] if row else None

    def get_str(self, content_hash: str) -> str | None:
        row = self.conn.execute(
            "SELECT content, encoding FROM archive WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        data, enc = row
        return data.decode(enc or "utf-8")

    def info(self, content_hash: str) -> ArchiveEntry | None:
        row = self.conn.execute(
            """
            SELECT content_hash, size_bytes, content_type, encoding,
                   created_at, refcount, sealed, signature
            FROM archive WHERE content_hash = ?
            """,
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        return ArchiveEntry(
            content_hash=row[0], size_bytes=row[1], content_type=row[2],
            encoding=row[3], created_at=row[4], refcount=row[5],
            sealed=bool(row[6]), signature=row[7],
        )

    # ── Verify ───────────────────────────────────────────────────────

    def verify(self, content_hash: str) -> bool:
        """Re-hash the stored content and confirm it matches the key.

        Defends against silent corruption. A False return means the
        content has been tampered with — investigate immediately.
        """
        row = self.conn.execute(
            "SELECT content FROM archive WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if row is None:
            return False
        return sha256_hex(row[0]) == content_hash

    def verify_all(self) -> dict[str, bool]:
        """Verify every blob in the archive. Returns {hash: ok}."""
        rows = self.conn.execute("SELECT content_hash FROM archive").fetchall()
        return {h: self.verify(h) for (h,) in rows}

    # ── Seal & sign ──────────────────────────────────────────────────

    def seal(self, content_hash: str) -> None:
        """Mark a blob as immutable forever. Cannot be undone."""
        with self._writer_tx():
            self.conn.execute(
                "UPDATE archive SET sealed = 1 WHERE content_hash = ?",
                (content_hash,),
            )

    def attach_signature(self, content_hash: str, signature: str) -> None:
        """Attach a detached cryptographic signature to a blob.

        The signature is opaque to the archive — the operator chooses
        the signing scheme (GPG, age, etc). What we promise is to store
        and return it verbatim.
        """
        with self._writer_tx():
            self.conn.execute(
                "UPDATE archive SET signature = ? WHERE content_hash = ?",
                (signature, content_hash),
            )

    # ── Refcount management ─────────────────────────────────────────

    def remove_ref(
        self,
        content_hash: str,
        *,
        ref_kind: str,
        ref_id: str,
    ) -> None:
        """Mark a reference as removed and decrement refcount.

        Does NOT delete the blob. Garbage collection (delete when
        refcount == 0 and not sealed) is a separate, explicit operator
        action via ``gc()``.
        """
        rid = self._ref_id(content_hash, ref_kind, ref_id)
        now = self._now()
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT removed_at FROM archive_refs WHERE ref_id = ?",
                (rid,),
            ).fetchone()
            if row is None or row[0] is not None:
                return
            self.conn.execute(
                "UPDATE archive_refs SET removed_at = ? WHERE ref_id = ?",
                (now, rid),
            )
            self.conn.execute(
                "UPDATE archive SET refcount = MAX(refcount - 1, 0) "
                "WHERE content_hash = ?",
                (content_hash,),
            )

    def gc(self, *, dry_run: bool = False) -> list[str]:
        """Delete unreferenced, unsealed blobs. Returns the hashes affected.

        Sealed blobs are NEVER deleted, even at refcount 0. This is the
        durability promise of sealing.
        """
        candidates = self.conn.execute(
            "SELECT content_hash FROM archive WHERE refcount = 0 AND sealed = 0"
        ).fetchall()
        hashes = [r[0] for r in candidates]
        if dry_run:
            return hashes
        with self._writer_tx():
            for h in hashes:
                self.conn.execute(
                    "DELETE FROM archive_refs WHERE content_hash = ?", (h,)
                )
                self.conn.execute(
                    "DELETE FROM archive WHERE content_hash = ?", (h,)
                )
        return hashes

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self) -> ArchiveStats:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0), "
            "       COALESCE(SUM(sealed), 0), "
            "       COUNT(DISTINCT content_type), "
            "       COALESCE(AVG(refcount), 0.0) "
            "FROM archive"
        ).fetchone()
        return ArchiveStats(
            total_objects=row[0],
            total_bytes=int(row[1] or 0),
            sealed_objects=int(row[2] or 0),
            unique_content_types=row[3],
            avg_refcount=float(row[4] or 0.0),
        )


__all__ = [
    "ContentArchive", "ArchiveEntry", "ArchiveStats",
    "sha256_hex", "ensure_archive_schema",
]
