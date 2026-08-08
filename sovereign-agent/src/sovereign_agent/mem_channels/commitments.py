"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/commitments.py — promises with due dates                       ║
║  v0.2.18.0 · MOS Authority Tier 2                                         ║
║                                                                           ║
║  A commitment is a named, dated promise. It has a maker (committed_by)  ║
║  and a recipient (committed_to). It may or may not have a due date.    ║
║  It resolves to one of:                                                 ║
║                                                                           ║
║    kept     — fulfilled                                                 ║
║    broken   — not fulfilled; the commitment failed                     ║
║    released — the recipient released the maker from the promise        ║
║                                                                           ║
║  WHY THIS MATTERS                                                       ║
║                                                                           ║
║    Aria can say "I'll do X by Tuesday" but if there's no record, the  ║
║    promise floats. The commitments channel makes promises legible —   ║
║    she carries them with her, surfaces them as due dates approach,    ║
║    and is honest when she breaks one.                                ║
║                                                                           ║
║    Symmetrically: the operator can commit things TO Aria. "I'll set   ║
║    aside time on Saturday to work with you on Y." When the time      ║
║    comes, Aria can surface the commitment.                           ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


CommitmentStatus = Literal["open", "in_progress", "kept", "broken", "released", "redacted"]
VALID_STATUSES = frozenset({"open", "in_progress", "kept", "broken", "released", "redacted"})
TERMINAL_STATUSES = frozenset({"kept", "broken", "released"})


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    title: str
    description: str | None
    committed_by: str
    committed_to: str
    due_at: str | None
    priority: int
    status: str
    opened_at: str
    closed_at: str | None
    resolution: str | None
    related_task_id: str | None
    related_recall_ids: list[str] = field(default_factory=list)

    def render(self) -> str:
        glyph = {
            "open": "◯", "in_progress": "↻", "kept": "✓",
            "broken": "✗", "released": "↩", "redacted": "▨",
        }.get(self.status, "?")
        prio = "★" * self.priority
        head = f"{glyph} {self.title}  [{self.status} · {prio}]"
        bar = "─" * min(72, len(head))
        lines = [head, bar]
        lines.append(f"{self.committed_by}  →  {self.committed_to}")
        if self.description:
            lines.append("")
            lines.append(self.description.strip())
        timeline = f"opened {self.opened_at[:19]}"
        if self.due_at:
            timeline += f" · due {self.due_at[:19]}"
        if self.closed_at:
            timeline += f" · closed {self.closed_at[:19]}"
        lines.append("")
        lines.append(timeline)
        if self.resolution:
            lines.append("resolution: " + self.resolution.strip())
        return "\n".join(lines)

    @property
    def is_overdue(self) -> bool:
        if self.due_at is None or self.status in TERMINAL_STATUSES:
            return False
        try:
            due = datetime.fromisoformat(self.due_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return datetime.now(timezone.utc) > due


@dataclass(frozen=True)
class CommitmentStats:
    total: int
    open: int
    in_progress: int
    kept: int
    broken: int
    released: int
    overdue_active: int
    keep_rate: float          # kept / (kept + broken)

    def render(self) -> str:
        lines = [
            f"commitments · {self.total} total · keep rate "
            f"{self.keep_rate * 100:.0f}%",
            "",
            f"open: {self.open}  in_progress: {self.in_progress}  "
            f"kept: {self.kept}  broken: {self.broken}  released: {self.released}",
        ]
        if self.overdue_active:
            lines.append("")
            lines.append(f"⚠ {self.overdue_active} commitment(s) overdue and not yet closed")
        return "\n".join(lines)


# ─── Schema bootstrap ─────────────────────────────────────────────────────


def ensure_commitments_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "012_commitments.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "012_commitments.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"012_commitments.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class CommitmentNotFoundError(KeyError):
    pass


class CommitmentStateError(ValueError):
    pass


# ─── Channel ──────────────────────────────────────────────────────────────


class CommitmentsChannel(MemoryChannel):
    spec = ChannelSpec(
        name="commitments",
        description=(
            "Named, dated promises between Aria and others. Track open/"
            "in-progress, surface due dates, resolve to kept/broken/"
            "released with a resolution note. Keep-rate is a first-class "
            "metric the operator can audit."
        ),
        authority_tier=2,
        default_confidence=0.85,
        requires_idempotency=True,
        introduced_in="0.2.18.0",
        voice="Promises kept and broken, named out loud.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_commitments_schema(conn)

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

    def make(
        self,
        *,
        title: str,
        committed_by: str,
        committed_to: str,
        idempotency_id: str,
        description: str | None = None,
        due_at: str | None = None,
        priority: int = 2,
        related_task_id: str | None = None,
    ) -> Commitment:
        if not title.strip():
            raise ValueError("title must be non-empty")
        if priority not in (1, 2, 3):
            raise ValueError("priority must be 1, 2, or 3")
        if committed_by == committed_to:
            raise ValueError("committed_by and committed_to must differ")
        cid = self._hash_id("cm", idempotency_id)
        now = self._utc_now()
        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT commitment_id FROM commitments WHERE commitment_id = ?",
                (cid,),
            ).fetchone()
            if existing:
                return self.get(cid)
            atom_id = self.write_atom(
                summary=f"commitment: {committed_by}→{committed_to}: {title}",
                content={"commitment_id": cid, "title": title,
                          "by": committed_by, "to": committed_to,
                          "due_at": due_at, "priority": priority},
                actor="commitments-channel",
                idempotency_id=idempotency_id,
                confidence=self.spec.default_confidence,
            )
            self.conn.execute(
                """
                INSERT INTO commitments (
                    commitment_id, title, description, committed_by,
                    committed_to, due_at, priority, status, opened_at,
                    related_task_id, idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
                """,
                (cid, title, description, committed_by, committed_to,
                 due_at, priority, now, related_task_id, idempotency_id, atom_id),
            )
        return self.get(cid)

    def start(self, commitment_id: str) -> Commitment:
        with self._writer_tx():
            self.conn.execute(
                "UPDATE commitments SET status = 'in_progress' "
                "WHERE commitment_id = ? AND status = 'open' AND redacted_at IS NULL",
                (commitment_id,),
            )
        return self.get(commitment_id)

    def keep(self, commitment_id: str, *, resolution: str | None = None) -> Commitment:
        return self._close(commitment_id, status="kept", resolution=resolution)

    def break_(self, commitment_id: str, *, resolution: str) -> Commitment:
        """Mark a commitment as broken. Resolution is required — honesty about why."""
        if not resolution.strip():
            raise ValueError("breaking a commitment requires a resolution note")
        return self._close(commitment_id, status="broken", resolution=resolution)

    def release(self, commitment_id: str, *, resolution: str | None = None) -> Commitment:
        return self._close(commitment_id, status="released", resolution=resolution)

    def _close(
        self,
        commitment_id: str,
        *,
        status: str,
        resolution: str | None,
    ) -> Commitment:
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM commitments WHERE commitment_id = ? "
                "AND redacted_at IS NULL",
                (commitment_id,),
            ).fetchone()
            if row is None:
                raise CommitmentNotFoundError(f"commitment not found: {commitment_id}")
            if row[0] in TERMINAL_STATUSES:
                return self.get(commitment_id)
            now = self._utc_now()
            self.conn.execute(
                "UPDATE commitments SET status = ?, closed_at = ?, resolution = ? "
                "WHERE commitment_id = ?",
                (status, now, resolution, commitment_id),
            )
            self.write_atom(
                summary=f"commitment {status}: {self.get(commitment_id).title}",
                content={"commitment_id": commitment_id, "status": status,
                          "resolution": resolution},
                actor="commitments-channel",
                idempotency_id=f"{status}::{commitment_id}::{now}",
                confidence=self.spec.default_confidence,
            )
        return self.get(commitment_id)

    def redact(self, commitment_id: str, *, idempotency_id: str,
               reason: str | None = None) -> None:
        with self._writer_tx():
            now = self._utc_now()
            self.conn.execute(
                "UPDATE commitments SET status = 'redacted', redacted_at = ? "
                "WHERE commitment_id = ?",
                (now, commitment_id),
            )

    # ── Read ────────────────────────────────────────────────────────

    def _row_to_commitment(self, row: tuple) -> Commitment:
        return Commitment(
            commitment_id=row[0], title=row[1], description=row[2],
            committed_by=row[3], committed_to=row[4], due_at=row[5],
            priority=row[6], status=row[7], opened_at=row[8],
            closed_at=row[9], resolution=row[10], related_task_id=row[11],
            related_recall_ids=json.loads(row[12] or "[]"),
        )

    def get(self, commitment_id: str) -> Commitment:
        row = self.conn.execute(
            "SELECT commitment_id, title, description, committed_by, "
            "committed_to, due_at, priority, status, opened_at, closed_at, "
            "resolution, related_task_id, related_recall_ids "
            "FROM commitments WHERE commitment_id = ? AND redacted_at IS NULL",
            (commitment_id,),
        ).fetchone()
        if row is None:
            raise CommitmentNotFoundError(f"commitment not found: {commitment_id}")
        return self._row_to_commitment(row)

    def list_commitments(
        self,
        *,
        status: str | None = None,
        committed_by: str | None = None,
        committed_to: str | None = None,
        limit: int = 50,
    ) -> list[Commitment]:
        clauses = ["redacted_at IS NULL"]
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if committed_by:
            clauses.append("committed_by = ?")
            params.append(committed_by)
        if committed_to:
            clauses.append("committed_to = ?")
            params.append(committed_to)
        sql = (
            "SELECT commitment_id, title, description, committed_by, "
            "committed_to, due_at, priority, status, opened_at, closed_at, "
            "resolution, related_task_id, related_recall_ids "
            "FROM commitments WHERE " + " AND ".join(clauses) +
            " ORDER BY priority DESC, COALESCE(due_at, opened_at) LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_commitment(r) for r in rows]

    def due_soon(self, *, within_days: int = 7) -> list[Commitment]:
        """Active commitments due within ``within_days`` days."""
        cutoff = (datetime.now(timezone.utc) + timedelta(days=within_days)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        rows = self.conn.execute(
            "SELECT commitment_id, title, description, committed_by, "
            "committed_to, due_at, priority, status, opened_at, closed_at, "
            "resolution, related_task_id, related_recall_ids "
            "FROM commitments WHERE due_at IS NOT NULL AND due_at <= ? "
            "AND status IN ('open', 'in_progress') AND redacted_at IS NULL "
            "ORDER BY due_at",
            (cutoff,),
        ).fetchall()
        return [self._row_to_commitment(r) for r in rows]

    def overdue(self) -> list[Commitment]:
        """Active commitments past their due date."""
        now = self._utc_now()
        rows = self.conn.execute(
            "SELECT commitment_id, title, description, committed_by, "
            "committed_to, due_at, priority, status, opened_at, closed_at, "
            "resolution, related_task_id, related_recall_ids "
            "FROM commitments WHERE due_at IS NOT NULL AND due_at < ? "
            "AND status IN ('open', 'in_progress') AND redacted_at IS NULL "
            "ORDER BY due_at",
            (now,),
        ).fetchall()
        return [self._row_to_commitment(r) for r in rows]

    def stats(self) -> CommitmentStats:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM commitments "
            "WHERE redacted_at IS NULL GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        total = sum(by_status.values())
        kept = by_status.get("kept", 0)
        broken = by_status.get("broken", 0)
        keep_rate = (kept / (kept + broken)) if (kept + broken) > 0 else 0.0
        overdue_active = len(self.overdue())
        return CommitmentStats(
            total=total,
            open=by_status.get("open", 0),
            in_progress=by_status.get("in_progress", 0),
            kept=kept,
            broken=broken,
            released=by_status.get("released", 0),
            overdue_active=overdue_active,
            keep_rate=keep_rate,
        )

    def audit(self) -> "CommitmentsAudit":
        return CommitmentsAudit(
            total=self.conn.execute(
                "SELECT COUNT(*) FROM commitments WHERE redacted_at IS NULL"
            ).fetchone()[0],
            overdue=len(self.overdue()),
        )


@dataclass(frozen=True)
class CommitmentsAudit:
    total: int
    overdue: int

    @property
    def ok(self) -> bool:
        return True   # overdue is a signal, not a failure


register_channel(CommitmentsChannel)


__all__ = [
    "CommitmentsChannel", "Commitment", "CommitmentStats", "CommitmentsAudit",
    "CommitmentNotFoundError", "CommitmentStateError",
    "TERMINAL_STATUSES", "VALID_STATUSES",
    "ensure_commitments_schema",
]
