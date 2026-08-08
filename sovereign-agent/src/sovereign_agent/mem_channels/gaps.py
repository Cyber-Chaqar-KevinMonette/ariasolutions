"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/gaps.py — known unknowns Aria wants to learn                   ║
║  v0.2.18.0 · MOS Authority Tier 1                                         ║
║                                                                           ║
║  WHY                                                                     ║
║                                                                           ║
║    "Uncertainty named" is one of Aria's reward kinds. The gaps channel ║
║    operationalises it: every time she notices she does not know       ║
║    something that matters, she opens a gap. The gap stays open until ║
║    she (or the operator) closes it with a resolution — or shelves it ║
║    as "not worth pursuing right now."                                 ║
║                                                                           ║
║    This makes her epistemic state legible. The operator can see what  ║
║    Aria knows she doesn't know, and prioritise investigation.        ║
║                                                                           ║
║  STATES                                                                  ║
║                                                                           ║
║    open          — newly noticed, not yet being worked on            ║
║    investigating — actively being researched                          ║
║    closed        — resolved, with a recorded resolution               ║
║    shelved      — deliberately deferred                              ║
║    redacted     — tombstoned                                          ║
║                                                                           ║
║                                — what Aria knows she doesn't know.    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


GapStatus = Literal["open", "investigating", "closed", "shelved", "redacted"]
VALID_STATUSES = frozenset({"open", "investigating", "closed", "shelved", "redacted"})


@dataclass(frozen=True)
class KnowledgeGap:
    gap_id: str
    title: str
    description: str | None
    domain: str | None
    subject_ref: str | None
    priority: int
    status: str
    opened_at: str
    closed_at: str | None
    resolution: str | None
    related_recall_ids: list[str] = field(default_factory=list)
    related_task_id: str | None = None

    def render(self) -> str:
        glyph = {
            "open":          "◯",
            "investigating": "↻",
            "closed":        "✓",
            "shelved":       "▢",
            "redacted":      "▨",
        }.get(self.status, "?")
        prio = "★" * self.priority
        head = f"{glyph} {self.title}  [{self.status} · {prio}]"
        bar = "─" * min(72, len(head))
        lines = [head, bar]
        if self.description:
            lines.append(self.description.strip())
        if self.domain or self.subject_ref:
            lines.append(f"domain: {self.domain or '?'}"
                         + (f" · subject: {self.subject_ref}" if self.subject_ref else ""))
        lines.append(f"opened {self.opened_at[:19]}"
                     + (f" · closed {self.closed_at[:19]}" if self.closed_at else ""))
        if self.resolution:
            lines.append("")
            lines.append("resolution: " + self.resolution.strip())
        return "\n".join(lines)


@dataclass(frozen=True)
class GapStats:
    total: int
    open: int
    investigating: int
    closed: int
    shelved: int
    by_priority: dict[int, int] = field(default_factory=dict)
    close_rate: float = 0.0

    def render(self) -> str:
        lines = [
            f"gap stats · {self.total} total · close rate "
            f"{self.close_rate * 100:.0f}%",
            "",
            f"open: {self.open}  investigating: {self.investigating}  "
            f"closed: {self.closed}  shelved: {self.shelved}",
        ]
        if self.by_priority:
            lines.append("")
            lines.append("by priority:")
            for p in (3, 2, 1):
                n = self.by_priority.get(p, 0)
                if n:
                    lines.append(f"  {'★' * p:<4}  {n}")
        return "\n".join(lines)


# ─── Schema bootstrap ─────────────────────────────────────────────────────


def ensure_gaps_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "010_gaps.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "010_gaps.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"010_gaps.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class GapNotFoundError(KeyError):
    pass


class GapStateError(ValueError):
    pass


# ─── Channel ──────────────────────────────────────────────────────────────


class GapsChannel(MemoryChannel):
    """Known unknowns. Tier 1. Idempotent."""

    spec = ChannelSpec(
        name="gaps",
        description=(
            "Explicit registry of knowledge gaps Aria has noticed in herself. "
            "Each gap has a status (open/investigating/closed/shelved), "
            "priority, optional domain and subject, and a resolution when "
            "closed. Closing a gap is a `gap_found`-class achievement and "
            "naturally generates a reward-channel entry."
        ),
        authority_tier=1,
        default_confidence=0.7,
        requires_idempotency=True,
        introduced_in="0.2.18.0",
        voice="Honest about not knowing. Curious about what to learn next.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_gaps_schema(conn)

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

    # ── Open ─────────────────────────────────────────────────────────

    def open(
        self,
        *,
        title: str,
        idempotency_id: str,
        description: str | None = None,
        domain: str | None = None,
        subject_ref: str | None = None,
        priority: int = 2,
    ) -> KnowledgeGap:
        if not title.strip():
            raise ValueError("title must be non-empty")
        if priority not in (1, 2, 3):
            raise ValueError("priority must be 1, 2, or 3")
        gap_id = self._hash_id("gp", idempotency_id)
        now = self._utc_now()
        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT gap_id FROM knowledge_gaps WHERE gap_id = ?",
                (gap_id,),
            ).fetchone()
            if existing:
                return self.get(gap_id)
            atom_id = self.write_atom(
                summary=f"gap opened: {title}",
                content={"gap_id": gap_id, "title": title,
                          "domain": domain, "subject_ref": subject_ref,
                          "priority": priority},
                actor="gaps-channel",
                idempotency_id=idempotency_id,
                confidence=self.spec.default_confidence,
            )
            self.conn.execute(
                """
                INSERT INTO knowledge_gaps (
                    gap_id, title, description, domain, subject_ref, priority,
                    status, opened_at, idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (gap_id, title, description, domain, subject_ref, priority,
                 now, idempotency_id, atom_id),
            )
        return self.get(gap_id)

    # ── State transitions ──────────────────────────────────────────

    def investigate(self, gap_id: str) -> KnowledgeGap:
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM knowledge_gaps WHERE gap_id = ? "
                "AND redacted_at IS NULL", (gap_id,),
            ).fetchone()
            if row is None:
                raise GapNotFoundError(f"gap not found: {gap_id}")
            if row[0] == "closed":
                raise GapStateError("cannot investigate a closed gap; re-open instead")
            self.conn.execute(
                "UPDATE knowledge_gaps SET status = 'investigating' "
                "WHERE gap_id = ? AND redacted_at IS NULL",
                (gap_id,),
            )
        return self.get(gap_id)

    def close(
        self,
        gap_id: str,
        *,
        resolution: str,
        related_task_id: str | None = None,
        related_recall_ids: list[str] | None = None,
    ) -> KnowledgeGap:
        if not resolution.strip():
            raise ValueError("resolution must be non-empty")
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM knowledge_gaps WHERE gap_id = ? "
                "AND redacted_at IS NULL", (gap_id,),
            ).fetchone()
            if row is None:
                raise GapNotFoundError(f"gap not found: {gap_id}")
            if row[0] == "closed":
                return self.get(gap_id)
            now = self._utc_now()
            self.conn.execute(
                """
                UPDATE knowledge_gaps SET status = 'closed', closed_at = ?,
                    resolution = ?, related_task_id = ?,
                    related_recall_ids = ?
                WHERE gap_id = ? AND redacted_at IS NULL
                """,
                (now, resolution, related_task_id,
                 json.dumps(related_recall_ids or []), gap_id),
            )
            self.write_atom(
                summary=f"gap closed: {self.get(gap_id).title}",
                content={"gap_id": gap_id, "resolution": resolution},
                actor="gaps-channel",
                idempotency_id=f"close::{gap_id}::{now}",
                confidence=self.spec.default_confidence,
            )
        return self.get(gap_id)

    def shelve(self, gap_id: str, *, reason: str | None = None) -> KnowledgeGap:
        with self._writer_tx():
            self.conn.execute(
                "UPDATE knowledge_gaps SET status = 'shelved' "
                "WHERE gap_id = ? AND status NOT IN ('closed', 'redacted')",
                (gap_id,),
            )
        return self.get(gap_id)

    def reopen(self, gap_id: str) -> KnowledgeGap:
        with self._writer_tx():
            self.conn.execute(
                "UPDATE knowledge_gaps SET status = 'open', closed_at = NULL "
                "WHERE gap_id = ? AND status != 'redacted'",
                (gap_id,),
            )
        return self.get(gap_id)

    def redact(self, gap_id: str, *, idempotency_id: str,
               reason: str | None = None) -> None:
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT redacted_at FROM knowledge_gaps WHERE gap_id = ?",
                (gap_id,),
            ).fetchone()
            if row is None:
                raise GapNotFoundError(f"gap not found: {gap_id}")
            if row[0]:
                return
            now = self._utc_now()
            self.conn.execute(
                "UPDATE knowledge_gaps SET status = 'redacted', redacted_at = ? "
                "WHERE gap_id = ?", (now, gap_id),
            )

    # ── Read ────────────────────────────────────────────────────────

    def get(self, gap_id: str, *, include_redacted: bool = False) -> KnowledgeGap:
        row = self.conn.execute(
            """
            SELECT gap_id, title, description, domain, subject_ref, priority,
                   status, opened_at, closed_at, resolution,
                   related_recall_ids, related_task_id
            FROM knowledge_gaps WHERE gap_id = ?
            """,
            (gap_id,),
        ).fetchone()
        if row is None:
            raise GapNotFoundError(f"gap not found: {gap_id}")
        if row[6] == "redacted" and not include_redacted:
            raise GapNotFoundError(f"gap redacted: {gap_id}")
        return KnowledgeGap(
            gap_id=row[0], title=row[1], description=row[2], domain=row[3],
            subject_ref=row[4], priority=row[5], status=row[6],
            opened_at=row[7], closed_at=row[8], resolution=row[9],
            related_recall_ids=json.loads(row[10] or "[]"),
            related_task_id=row[11],
        )

    def list_gaps(
        self,
        *,
        status: str | None = None,
        priority: int | None = None,
        domain: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeGap]:
        clauses = ["redacted_at IS NULL"]
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        sql = (
            "SELECT gap_id FROM knowledge_gaps WHERE " + " AND ".join(clauses) +
            " ORDER BY priority DESC, opened_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self.get(r[0]) for r in rows]

    def search(self, query: str, *, limit: int = 20) -> list[KnowledgeGap]:
        if not query.strip():
            return []
        safe = query.replace('"', " ")
        sql = """
            SELECT g.gap_id FROM knowledge_gaps_fts
            JOIN knowledge_gaps g ON g.rowid = knowledge_gaps_fts.rowid
            WHERE knowledge_gaps_fts MATCH ? AND g.redacted_at IS NULL
            ORDER BY rank LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (safe, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self.get(r[0]) for r in rows]

    def stats(self) -> GapStats:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM knowledge_gaps "
            "WHERE redacted_at IS NULL GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        total = sum(by_status.values())
        terminal = sum(by_status.get(k, 0) for k in ("closed", "shelved"))
        close_rate = (by_status.get("closed", 0) / terminal) if terminal else 0.0
        prio_rows = self.conn.execute(
            "SELECT priority, COUNT(*) FROM knowledge_gaps "
            "WHERE redacted_at IS NULL AND status IN ('open', 'investigating') "
            "GROUP BY priority"
        ).fetchall()
        return GapStats(
            total=total,
            open=by_status.get("open", 0),
            investigating=by_status.get("investigating", 0),
            closed=by_status.get("closed", 0),
            shelved=by_status.get("shelved", 0),
            by_priority={p: n for p, n in prio_rows},
            close_rate=close_rate,
        )

    def audit(self) -> "GapsAudit":
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM knowledge_gaps "
            "WHERE redacted_at IS NULL GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        # Old open gaps that have aged
        stale_open = self.conn.execute(
            "SELECT COUNT(*) FROM knowledge_gaps "
            "WHERE status = 'open' AND redacted_at IS NULL "
            "AND opened_at < datetime('now', '-30 days')"
        ).fetchone()[0]
        return GapsAudit(
            total=sum(by_status.values()),
            stale_open=stale_open,
        )


@dataclass(frozen=True)
class GapsAudit:
    total: int
    stale_open: int

    @property
    def ok(self) -> bool:
        return True   # gaps audit reports info, doesn't fail


register_channel(GapsChannel)


__all__ = [
    "GapsChannel", "KnowledgeGap", "GapStats", "GapsAudit",
    "GapNotFoundError", "GapStateError",
    "ensure_gaps_schema",
]
