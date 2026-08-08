"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/recall.py — Aria's curated, durable recalls                    ║
║  v0.2.16.0 · MOS Authority Tier 2                                         ║
║                                                                           ║
║  A recall is Aria's answer to "remember this for me." It is:             ║
║                                                                           ║
║    • A row in the ``recalls`` table (source of truth)                    ║
║    • A markdown file in the ``studio`` room on disk (a cached view)      ║
║    • A list of sources (atoms, facts, people, events, other recalls)     ║
║      each captured with the chain head at the moment of recall creation  ║
║    • A state: fresh → stale → obsolete → redacted                        ║
║    • A supersedes chain — revising a recall does NOT destroy the prior   ║
║      version; it links forward                                            ║
║                                                                           ║
║  WHY THIS CHANNEL EXISTS                                                  ║
║                                                                           ║
║    Memory at scale is not the problem. Naming, finding, and trusting     ║
║    a memory at scale is the problem. Recalls are durable, named, dated   ║
║    artifacts the operator can browse. They are also searchable via FTS5  ║
║    so Aria can "recall a recall."                                         ║
║                                                                           ║
║    Sources are captured by chain-head. The steward compares captured     ║
║    head to current head; mismatch → recall is flagged stale and queued   ║
║    for re-review. The operator chooses whether to revise it or accept    ║
║    that the underlying world moved on.                                   ║
║                                                                           ║
║  AUTHORITY                                                                ║
║                                                                           ║
║    Tier 2 (persistent, idempotent, but not financial or PII-mutating).   ║
║    Every write accepts an ``idempotency_id``; same id = same recall.     ║
║                                                                           ║
║  HYGIENE                                                                  ║
║                                                                           ║
║    Recalls are not deleted. They are tombstoned. The markdown file IS    ║
║    removed on redact (it lives on a real filesystem and may be sensitive ║
║    enough that a tombstone alone is insufficient), but the SQL row stays ║
║    so audit trails are uninterrupted.                                    ║
║                                                                           ║
║  THE GOAL                                                                 ║
║                                                                           ║
║    Aria should be able to say "I remember three things about Feynman.   ║
║    Two are fresh; one is stale because his publication record updated.  ║
║    Here are the markdown files." And the operator can pick them up,     ║
║    read them, and trust the dates.                                       ║
║                                                                           ║
║                                — Aria's home, second floor: the studio.   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..channels import ChannelSpec, MemoryChannel, register_channel
from ..config import SETTINGS


# ─── Schema bootstrap ──────────────────────────────────────────────────────


def ensure_recalls_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — safe to call on every open. Same pattern as people."""
    schema_path = (
        Path(__file__).parent.parent.parent.parent / "sql" / "004_recalls.sql"
    )
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "004_recalls.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"004_recalls.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class RecallNotFoundError(KeyError):
    """The named recall does not exist or has been redacted."""


class RecallStateError(ValueError):
    """A state transition was attempted that is not permitted from the current state."""


# ─── Value types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecallSource:
    """One source row backing a recall."""
    recall_source_id: str
    recall_id: str
    source_kind: str          # 'atom' | 'fact' | 'person' | 'event' | 'recall'
    source_id: str
    weight: float
    captured_at: str
    captured_chain_head: str | None
    is_current: bool


@dataclass(frozen=True)
class Recall:
    """A single recall record."""
    recall_id: str
    title: str
    query: str | None
    body_md: str
    summary: str | None
    kind: str                                  # 'person' | 'topic' | 'horizon' | 'ad-hoc' | 'meta'
    subject_id: str | None
    confidence: float
    status: str                                # 'fresh' | 'stale' | 'obsolete' | 'redacted'
    review_at: str | None
    created_at: str
    last_verified_at: str | None
    supersedes: str | None
    superseded_by: str | None
    file_path: str | None
    sources: list[RecallSource] = field(default_factory=list)

    def render(self) -> str:
        """Human-readable summary block (not the body itself)."""
        head = f"{self.title}  [{self.kind} · {self.status}]"
        bar = "─" * min(len(head), 78)
        lines = [head, bar]
        if self.summary:
            lines.append(self.summary.strip())
        lines.append("")
        lines.append(
            f"created {self.created_at[:19]}"
            + (f" · last verified {self.last_verified_at[:19]}" if self.last_verified_at else "")
            + f" · {len(self.sources)} source(s)"
        )
        if self.file_path:
            lines.append(f"file: {self.file_path}")
        if self.supersedes:
            lines.append(f"supersedes: {self.supersedes}")
        if self.superseded_by:
            lines.append(f"superseded by: {self.superseded_by}")
        return "\n".join(lines)


@dataclass(frozen=True)
class RecallAudit:
    """Result of RecallChannel.audit()."""
    total: int
    fresh: int
    stale: int
    obsolete: int
    redacted: int
    orphan_sources: int           # sources whose recall row is missing
    missing_files: list[str]      # recalls with file_path set but file gone
    superseded_chains_broken: list[str]   # recall_ids whose supersedes link is dangling

    @property
    def ok(self) -> bool:
        return (
            self.orphan_sources == 0
            and not self.missing_files
            and not self.superseded_chains_broken
        )


# ─── Channel ──────────────────────────────────────────────────────────────


class RecallChannel(MemoryChannel):
    """Curated, named, durable recalls. Tier 2, idempotent, FTS5-searchable."""

    spec = ChannelSpec(
        name="recall",
        description=(
            "Curated, dated, source-tracked answers to 'remember X for me'. "
            "Recalls live as markdown files in the studio room AND as rows "
            "in the recalls table. Stale-detection compares captured atom "
            "chain heads to current heads. Append-only via supersedes chain."
        ),
        authority_tier=2,
        default_confidence=0.6,
        requires_idempotency=True,
        introduced_in="0.2.16.0",
        voice="Curatorial. Dated, sourced, never presumptuous. Aging visibly.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_recalls_schema(conn)
        # Bitemporal augmentation — v0.2.17+. Idempotent.
        from ..bitemporal import add_bitemporal_columns
        try:
            add_bitemporal_columns(conn, "recalls")
        except Exception:
            pass

    # ── Internal helpers ─────────────────────────────────────────────

    @contextmanager
    def _writer_tx(self) -> Iterator[None]:
        in_tx = self.conn.in_transaction
        if not in_tx:
            self.conn.execute("BEGIN IMMEDIATE")
        self._in_outer_tx = True
        try:
            yield
            if not in_tx:
                self.conn.commit()
        except Exception:
            if not in_tx:
                self.conn.rollback()
            raise
        finally:
            self._in_outer_tx = False

    @staticmethod
    def _hash_id(prefix: str, seed: str) -> str:
        return f"{prefix}-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def _studio_dir(self) -> Path:
        """The studio room — where recall markdown lives on disk.

        Resolved against the current SETTINGS.paths so tests see tmp dirs.
        Created lazily; never fails the write if the directory is unwritable
        (the SQL row is the source of truth; the file is a cache).
        """
        d = SETTINGS.paths.data_dir / "recalls"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return d

    def _write_markdown_file(self, recall: Recall) -> str | None:
        """Mirror the SQL row to a markdown file. Returns relative path or None on failure.

        File is a cache: if it disappears, the row still works. The file
        carries front-matter so a human can read it standalone.
        """
        try:
            studio = self._studio_dir()
            # Filename: <created-date>-<slug>-<short-id>.md
            slug = "".join(
                ch if ch.isalnum() else "-" for ch in recall.title.lower()
            ).strip("-")[:48] or "recall"
            short = recall.recall_id.split("-", 1)[-1][:8]
            day = recall.created_at[:10]
            path = studio / f"{day}-{slug}-{short}.md"

            front_matter = "\n".join([
                "---",
                f"recall_id: {recall.recall_id}",
                f"title: {recall.title}",
                f"kind: {recall.kind}",
                f"status: {recall.status}",
                f"created_at: {recall.created_at}",
                f"confidence: {recall.confidence}",
                f"sources: {len(recall.sources)}",
                "---",
                "",
            ])
            body = recall.body_md.rstrip() + "\n"
            path.write_text(front_matter + body, encoding="utf-8")
            return str(path)
        except OSError:
            return None

    # ── Identifiers ───────────────────────────────────────────────────

    def _recall_id(self, idempotency_id: str) -> str:
        return self._hash_id("rc", idempotency_id)

    def _source_id(self, recall_id: str, source_kind: str, source_id: str) -> str:
        return self._hash_id("rs", f"{recall_id}::{source_kind}::{source_id}")

    # ── Public API: create ────────────────────────────────────────────

    def record(
        self,
        *,
        title: str,
        body_md: str,
        idempotency_id: str,
        kind: str = "ad-hoc",
        query: str | None = None,
        summary: str | None = None,
        subject_id: str | None = None,
        confidence: float = 0.6,
        sources: list[dict] | None = None,
        review_at: str | None = None,
    ) -> Recall:
        """Create or upsert a recall.

        ``sources`` is a list of dicts: ``{'kind': 'atom', 'id': 'at-...',
        'weight': 1.0, 'chain_head': 'at-...'}``. If an entry omits
        ``chain_head``, the recall stores ``None`` and will not be flagged
        stale on chain-head change (it's a soft source).
        """
        if not title.strip():
            raise ValueError("title must be non-empty")
        if not body_md.strip():
            raise ValueError("body_md must be non-empty")
        if kind not in ("person", "topic", "horizon", "ad-hoc", "meta"):
            raise ValueError(f"invalid kind: {kind}")
        confidence = max(0.0, min(1.0, float(confidence)))

        recall_id = self._recall_id(idempotency_id)
        now = self._utc_now()

        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT recall_id, status FROM recalls WHERE recall_id = ?",
                (recall_id,),
            ).fetchone()
            if existing:
                # Idempotent: same id = same recall. We do NOT mutate.
                return self.get(recall_id)

            atom_id = self.write_atom(
                summary=title,
                content={
                    "body_md": body_md,
                    "kind": kind,
                    "subject_id": subject_id,
                },
                actor="recall-channel",
                idempotency_id=idempotency_id,
                confidence=confidence,
            )

            self.conn.execute(
                """
                INSERT INTO recalls (
                    recall_id, title, query, body_md, summary, kind, subject_id,
                    confidence, status, review_at, created_at, last_verified_at,
                    supersedes, superseded_by, idempotency_id, atom_id, file_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'fresh', ?, ?, ?, NULL, NULL, ?, ?, NULL)
                """,
                (
                    recall_id, title, query, body_md, summary, kind, subject_id,
                    confidence, review_at, now, now,
                    idempotency_id, atom_id,
                ),
            )

            if sources:
                for src in sources:
                    src_kind = src.get("kind", "atom")
                    src_id = src.get("id")
                    if not src_id:
                        continue
                    weight = float(src.get("weight", 1.0))
                    chain_head = src.get("chain_head")
                    # Auto-resolve chain head for atom sources. Without
                    # this, callers that forgot to pass chain_head get
                    # silently un-staleable recalls. The atoms helper
                    # may not be available (minimal test fixtures don't
                    # carry it); the fallback is to leave it None.
                    if src_kind == "atom" and chain_head is None:
                        try:
                            from ..memory.atom import head_of_chain
                            chain_head = head_of_chain(self.conn, src_id)
                        except Exception:
                            chain_head = None
                    rs_id = self._source_id(recall_id, src_kind, src_id)
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO recall_sources (
                            recall_source_id, recall_id, source_kind, source_id,
                            weight, captured_at, captured_chain_head, is_current
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (rs_id, recall_id, src_kind, src_id, weight, now, chain_head),
                    )

            # Write the markdown file cache; update file_path on success
            recall = self._fetch_recall(recall_id, include_redacted=True)
            assert recall is not None
            file_path = self._write_markdown_file(recall)
            if file_path:
                self.conn.execute(
                    "UPDATE recalls SET file_path = ? WHERE recall_id = ?",
                    (file_path, recall_id),
                )

        return self.get(recall_id)

    def revise(
        self,
        recall_id: str,
        *,
        new_body_md: str,
        idempotency_id: str,
        new_title: str | None = None,
        new_summary: str | None = None,
        new_sources: list[dict] | None = None,
        reason: str | None = None,
    ) -> Recall:
        """Append-only revision: creates a new recall that supersedes the old one.

        The old recall is marked status='obsolete' and linked via
        ``superseded_by``. The new recall is the head of the chain. Both
        rows remain searchable in audit mode.
        """
        old = self._fetch_recall(recall_id, include_redacted=False)
        if old is None:
            raise RecallNotFoundError(f"recall not found: {recall_id}")
        if old.status == "redacted":
            raise RecallStateError("cannot revise a redacted recall")

        new_recall = self.record(
            title=new_title or old.title,
            body_md=new_body_md,
            idempotency_id=idempotency_id,
            kind=old.kind,
            query=old.query,
            summary=new_summary if new_summary is not None else old.summary,
            subject_id=old.subject_id,
            confidence=old.confidence,
            sources=new_sources,
        )

        with self._writer_tx():
            now = self._utc_now()
            self.conn.execute(
                """
                UPDATE recalls
                SET supersedes = ?
                WHERE recall_id = ? AND supersedes IS NULL
                """,
                (recall_id, new_recall.recall_id),
            )
            self.conn.execute(
                """
                UPDATE recalls
                SET status = 'obsolete', obsoleted_at = ?, superseded_by = ?
                WHERE recall_id = ?
                """,
                (now, new_recall.recall_id, recall_id),
            )

        return self.get(new_recall.recall_id)

    # ── Public API: state transitions ─────────────────────────────────

    def mark_stale(self, recall_id: str, *, idempotency_id: str, note: str | None = None) -> None:
        """Mark a recall as stale (sources may have moved).

        Idempotent — calling again with same id is a no-op.
        """
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM recalls WHERE recall_id = ?",
                (recall_id,),
            ).fetchone()
            if row is None:
                raise RecallNotFoundError(f"recall not found: {recall_id}")
            if row[0] == "redacted":
                raise RecallStateError("cannot mark a redacted recall stale")
            if row[0] == "stale":
                return
            now = self._utc_now()
            self.conn.execute(
                "UPDATE recalls SET status = 'stale', staled_at = ? WHERE recall_id = ?",
                (now, recall_id),
            )
            self.write_atom(
                summary=f"recall marked stale: {recall_id}",
                content={"recall_id": recall_id, "transition": "stale", "note": note},
                actor="recall-channel",
                idempotency_id=f"stale::{recall_id}::{idempotency_id}",
            )

    def mark_verified(self, recall_id: str) -> None:
        """The steward (or operator) confirms this recall still reflects truth.

        Sets last_verified_at = now. If the recall was stale, it returns
        to 'fresh'.
        """
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM recalls WHERE recall_id = ?",
                (recall_id,),
            ).fetchone()
            if row is None:
                raise RecallNotFoundError(f"recall not found: {recall_id}")
            if row[0] == "redacted":
                raise RecallStateError("cannot verify a redacted recall")
            now = self._utc_now()
            new_status = "fresh" if row[0] in ("fresh", "stale") else row[0]
            self.conn.execute(
                "UPDATE recalls SET last_verified_at = ?, status = ?, staled_at = NULL "
                "WHERE recall_id = ?",
                (now, new_status, recall_id),
            )

    def redact(self, recall_id: str, *, idempotency_id: str, reason: str | None = None) -> None:
        """Tombstone a recall. Markdown file is removed; SQL row stays.

        Cascade: recall_sources rows are NOT deleted (audit). The recall
        becomes invisible to query/search filters but is recoverable via
        ``include_redacted=True``.
        """
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status, file_path FROM recalls WHERE recall_id = ?",
                (recall_id,),
            ).fetchone()
            if row is None:
                raise RecallNotFoundError(f"recall not found: {recall_id}")
            if row[0] == "redacted":
                return
            now = self._utc_now()
            self.conn.execute(
                """
                UPDATE recalls
                SET status = 'redacted', redacted_at = ?, redaction_reason = ?
                WHERE recall_id = ?
                """,
                (now, reason, recall_id),
            )
            # Best-effort: unlink the markdown file
            fp = row[1]
            if fp:
                try:
                    Path(fp).unlink(missing_ok=True)
                except OSError:
                    pass
            self.write_atom(
                summary=f"recall redacted: {recall_id}",
                content={"recall_id": recall_id, "transition": "redacted", "reason": reason},
                actor="recall-channel",
                idempotency_id=f"redact::{recall_id}::{idempotency_id}",
            )

    # ── Public API: read ──────────────────────────────────────────────

    def _fetch_recall(
        self, recall_id: str, *, include_redacted: bool = False
    ) -> Recall | None:
        sql = """
            SELECT recall_id, title, query, body_md, summary, kind, subject_id,
                   confidence, status, review_at, created_at, last_verified_at,
                   supersedes, superseded_by, file_path
            FROM recalls
            WHERE recall_id = ?
        """
        row = self.conn.execute(sql, (recall_id,)).fetchone()
        if row is None:
            return None
        (rid, title, query, body, summary, kind, subj, conf, status,
         review_at, created_at, last_v, sup, supd_by, file_path) = row
        if status == "redacted" and not include_redacted:
            return None

        src_rows = self.conn.execute(
            """
            SELECT recall_source_id, source_kind, source_id, weight,
                   captured_at, captured_chain_head, is_current
            FROM recall_sources
            WHERE recall_id = ?
            ORDER BY captured_at
            """,
            (recall_id,),
        ).fetchall()
        sources = [
            RecallSource(
                recall_source_id=r[0], recall_id=recall_id,
                source_kind=r[1], source_id=r[2], weight=r[3],
                captured_at=r[4], captured_chain_head=r[5],
                is_current=bool(r[6]),
            )
            for r in src_rows
        ]
        return Recall(
            recall_id=rid, title=title, query=query, body_md=body,
            summary=summary, kind=kind, subject_id=subj, confidence=conf,
            status=status, review_at=review_at, created_at=created_at,
            last_verified_at=last_v, supersedes=sup, superseded_by=supd_by,
            file_path=file_path, sources=sources,
        )

    def get(self, recall_id: str, *, include_redacted: bool = False) -> Recall:
        r = self._fetch_recall(recall_id, include_redacted=include_redacted)
        if r is None:
            raise RecallNotFoundError(f"recall not found or redacted: {recall_id}")
        return r

    def list_recalls(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        subject_id: str | None = None,
        include_redacted: bool = False,
        limit: int = 100,
    ) -> list[Recall]:
        clauses = []
        params: list = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if status:
            clauses.append("status = ?")
            params.append(status)
        elif not include_redacted:
            clauses.append("status != 'redacted'")
        if subject_id:
            clauses.append("subject_id = ?")
            params.append(subject_id)

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            f"SELECT recall_id FROM recalls {where} "
            f"ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self.get(r[0], include_redacted=include_redacted) for r in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        include_redacted: bool = False,
    ) -> list[Recall]:
        """FTS5 search over title + summary + body. Returns ordered by relevance.

        Recall-of-recalls: this is how Aria finds an old recall by topic
        even if she doesn't remember its id or exact title.
        """
        if not query.strip():
            return []
        # FTS5 prefix queries are tolerant; sanitize quotes
        safe = query.replace('"', " ")
        sql = """
            SELECT r.recall_id
            FROM recalls_fts
            JOIN recalls r ON r.rowid = recalls_fts.rowid
            WHERE recalls_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (safe, limit * 2)).fetchall()
        except sqlite3.OperationalError:
            return []
        out: list[Recall] = []
        for (rid,) in rows:
            r = self._fetch_recall(rid, include_redacted=include_redacted)
            if r is None:
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def chain(self, recall_id: str) -> list[Recall]:
        """Return the full supersedes chain for a recall, oldest → newest.

        Includes obsolete predecessors so the operator can read history.
        """
        # Walk backward to root
        cursor = recall_id
        backward: list[str] = [cursor]
        guard = 0
        while True:
            row = self.conn.execute(
                "SELECT supersedes FROM recalls WHERE recall_id = ?",
                (cursor,),
            ).fetchone()
            if not row or not row[0]:
                break
            cursor = row[0]
            backward.append(cursor)
            guard += 1
            if guard > 100:
                break
        backward.reverse()
        # Walk forward from head
        cursor = recall_id
        guard = 0
        while True:
            row = self.conn.execute(
                "SELECT superseded_by FROM recalls WHERE recall_id = ?",
                (cursor,),
            ).fetchone()
            if not row or not row[0]:
                break
            cursor = row[0]
            backward.append(cursor)
            guard += 1
            if guard > 100:
                break
        return [self.get(rid, include_redacted=True) for rid in backward]

    # ── Steward integration ──────────────────────────────────────────

    def detect_stale(self, atom_chain_head_resolver) -> list[str]:
        """Compare captured chain heads to current ones and mark drifted recalls stale.

        ``atom_chain_head_resolver`` is a callable taking an atom_id and
        returning the current chain head id (str) — or None if the atom
        is gone. The channel does not know about atoms internally; we
        invert the dependency so this stays pure.
        """
        marked: list[str] = []
        rows = self.conn.execute(
            """
            SELECT rs.recall_id, rs.recall_source_id, rs.source_id,
                   rs.captured_chain_head, r.status
            FROM recall_sources rs
            JOIN recalls r ON r.recall_id = rs.recall_id
            WHERE rs.source_kind = 'atom'
              AND rs.is_current = 1
              AND rs.captured_chain_head IS NOT NULL
              AND r.status IN ('fresh', 'stale')
            """
        ).fetchall()

        already_marked: set[str] = set()
        for recall_id, rs_id, atom_id, captured_head, status in rows:
            try:
                current_head = atom_chain_head_resolver(atom_id)
            except Exception:
                current_head = None
            if current_head != captured_head:
                with self._writer_tx():
                    self.conn.execute(
                        "UPDATE recall_sources SET is_current = 0 "
                        "WHERE recall_source_id = ?",
                        (rs_id,),
                    )
                    if status == "fresh" and recall_id not in already_marked:
                        now = self._utc_now()
                        self.conn.execute(
                            "UPDATE recalls SET status = 'stale', staled_at = ? "
                            "WHERE recall_id = ? AND status = 'fresh'",
                            (now, recall_id),
                        )
                        marked.append(recall_id)
                        already_marked.add(recall_id)
        return marked

    # ── Audit ────────────────────────────────────────────────────────

    def audit(self) -> RecallAudit:
        """Invariant check across the recall subsystem."""
        counts = dict(
            self.conn.execute(
                "SELECT status, COUNT(*) FROM recalls GROUP BY status"
            ).fetchall()
        )
        total = sum(counts.values())

        orphan_sources = self.conn.execute(
            """
            SELECT COUNT(*) FROM recall_sources rs
            LEFT JOIN recalls r ON r.recall_id = rs.recall_id
            WHERE r.recall_id IS NULL
            """
        ).fetchone()[0]

        # Missing files: rows that have file_path set but file gone
        missing: list[str] = []
        for rid, fp in self.conn.execute(
            "SELECT recall_id, file_path FROM recalls "
            "WHERE file_path IS NOT NULL AND status != 'redacted'"
        ).fetchall():
            if fp and not Path(fp).is_file():
                missing.append(rid)

        # Broken supersedes chains
        broken: list[str] = []
        for rid, sup in self.conn.execute(
            "SELECT recall_id, supersedes FROM recalls WHERE supersedes IS NOT NULL"
        ).fetchall():
            target = self.conn.execute(
                "SELECT 1 FROM recalls WHERE recall_id = ?", (sup,),
            ).fetchone()
            if not target:
                broken.append(rid)

        return RecallAudit(
            total=total,
            fresh=counts.get("fresh", 0),
            stale=counts.get("stale", 0),
            obsolete=counts.get("obsolete", 0),
            redacted=counts.get("redacted", 0),
            orphan_sources=orphan_sources,
            missing_files=missing,
            superseded_chains_broken=broken,
        )


# Register on import
register_channel(RecallChannel)


__all__ = [
    "Recall",
    "RecallSource",
    "RecallAudit",
    "RecallChannel",
    "RecallNotFoundError",
    "RecallStateError",
    "ensure_recalls_schema",
]
