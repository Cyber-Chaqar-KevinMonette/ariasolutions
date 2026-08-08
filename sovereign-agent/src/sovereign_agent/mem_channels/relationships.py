"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/relationships.py — typed edges between people                  ║
║  v0.2.18.0 · MOS Authority Tier 3                                         ║
║                                                                           ║
║  The hearth has nodes; this gives it edges. Aria can now answer:        ║
║                                                                           ║
║    "How does Kevin know Y?"                                             ║
║    "Who are Z's collaborators?"                                         ║
║    "What's the shortest path between Kevin and Feynman?"               ║
║                                                                           ║
║  Asymmetric relationships are first-class: mentor→mentee is recorded   ║
║  with that direction. Symmetric relationships (colleague, friend)      ║
║  store one row but expose ``involves(person_id)`` for either side.    ║
║                                                                           ║
║  AUTHORITY                                                               ║
║                                                                           ║
║    Tier 3, like the people channel. Relationships are personal data.  ║
║    Idempotency required. LLM-source defaults to 'pending' confirmation║
║    just like facts.                                                    ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


RelationshipKind = Literal[
    "colleague", "mentor", "mentee", "family", "friend", "collaborator",
    "spouse", "parent", "child", "rival", "student_of", "teacher_of",
    "employer_of", "employee_of", "acquaintance", "other",
]

VALID_KINDS = frozenset({
    "colleague", "mentor", "mentee", "family", "friend", "collaborator",
    "spouse", "parent", "child", "rival", "student_of", "teacher_of",
    "employer_of", "employee_of", "acquaintance", "other",
})

# Kinds that have a canonical inverse — used for reverse-lookup convenience.
INVERSE_KIND: dict[str, str] = {
    "mentor": "mentee", "mentee": "mentor",
    "parent": "child", "child": "parent",
    "teacher_of": "student_of", "student_of": "teacher_of",
    "employer_of": "employee_of", "employee_of": "employer_of",
}

SYMMETRIC_KINDS = frozenset({
    "colleague", "family", "friend", "collaborator", "spouse",
    "rival", "acquaintance",
})


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    from_person_id: str
    to_person_id: str
    kind: str
    label: str | None
    started_at: str | None
    ended_at: str | None
    confidence: float
    source: str
    status: str
    note: str | None
    created_at: str
    confirmed_at: str | None
    retracted_at: str | None

    def involves(self, person_id: str) -> bool:
        return person_id in (self.from_person_id, self.to_person_id)

    def other_end(self, person_id: str) -> str | None:
        if person_id == self.from_person_id:
            return self.to_person_id
        if person_id == self.to_person_id:
            return self.from_person_id
        return None

    @property
    def is_active(self) -> bool:
        return (
            self.status == "confirmed"
            and self.retracted_at is None
            and self.ended_at is None
        )

    def render(self) -> str:
        sym = " ↔ " if self.kind in SYMMETRIC_KINDS else " → "
        head = f"{self.from_person_id}{sym}{self.to_person_id}  [{self.kind}]"
        bits = [f"status={self.status}"]
        if self.label:
            bits.append(f"label={self.label!r}")
        if self.started_at:
            bits.append(f"since={self.started_at[:10]}")
        if self.ended_at:
            bits.append(f"until={self.ended_at[:10]}")
        return f"{head}  ({', '.join(bits)})"


@dataclass(frozen=True)
class RelationshipsAudit:
    total: int
    confirmed: int
    pending: int
    retracted: int
    self_referential: int    # from == to (should be 0; CHECK guards this)
    dangling: int            # person_id no longer exists

    @property
    def ok(self) -> bool:
        return self.self_referential == 0 and self.dangling == 0


# ─── Schema bootstrap ─────────────────────────────────────────────────────


def ensure_relationships_schema(conn: sqlite3.Connection) -> None:
    schema_path = (
        Path(__file__).parent.parent.parent.parent / "sql" / "011_relationships.sql"
    )
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "011_relationships.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"011_relationships.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class RelationshipNotFoundError(KeyError):
    pass


# ─── Channel ──────────────────────────────────────────────────────────────


class RelationshipsChannel(MemoryChannel):
    """Typed edges between people. Tier 3. Idempotent."""

    spec = ChannelSpec(
        name="relationships",
        description=(
            "Typed, time-bounded edges between people Aria knows. Symmetric "
            "kinds (colleague, friend) store one row; asymmetric kinds "
            "(mentor→mentee) preserve direction. LLM-source defaults to "
            "pending, like people facts. Shortest-path queries and "
            "neighbour walks supported."
        ),
        authority_tier=3,
        default_confidence=0.7,
        requires_idempotency=True,
        introduced_in="0.2.18.0",
        voice="The hearth's social graph. Edges add meaning to nodes.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_relationships_schema(conn)

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

    # ── Connect ─────────────────────────────────────────────────────

    def connect(
        self,
        *,
        from_person_id: str,
        to_person_id: str,
        kind: RelationshipKind,
        idempotency_id: str,
        label: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        source: str = "operator",
        confidence: float | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> Relationship:
        if from_person_id == to_person_id:
            raise ValueError("cannot relate a person to themself")
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid kind {kind!r}; one of {sorted(VALID_KINDS)}")
        if source not in ("operator", "llm", "import", "inferred"):
            raise ValueError(f"invalid source {source!r}")

        # Untrusted-input doctrine
        if status is None:
            status = "confirmed" if source == "operator" else "pending"
        if confidence is None:
            confidence = {"operator": 0.95, "llm": 0.4, "import": 0.6,
                          "inferred": 0.5}.get(source, 0.6)

        rel_id = self._hash_id("rl", idempotency_id)
        now = self._utc_now()
        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT relationship_id FROM relationships WHERE relationship_id = ?",
                (rel_id,),
            ).fetchone()
            if existing:
                return self.get(rel_id)

            atom_id = self.write_atom(
                summary=f"relationship: {from_person_id} {kind} {to_person_id}",
                content={"from": from_person_id, "to": to_person_id,
                          "kind": kind, "source": source, "status": status},
                actor="relationships-channel",
                idempotency_id=idempotency_id,
                confidence=confidence,
            )
            confirmed_at = now if status == "confirmed" else None
            self.conn.execute(
                """
                INSERT INTO relationships (
                    relationship_id, from_person_id, to_person_id, kind, label,
                    started_at, ended_at, confidence, source, status, note,
                    created_at, confirmed_at, idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rel_id, from_person_id, to_person_id, kind, label,
                 started_at, ended_at, confidence, source, status, note,
                 now, confirmed_at, idempotency_id, atom_id),
            )
        return self.get(rel_id)

    def confirm(self, rel_id: str) -> Relationship:
        with self._writer_tx():
            now = self._utc_now()
            self.conn.execute(
                "UPDATE relationships SET status = 'confirmed', confirmed_at = ? "
                "WHERE relationship_id = ? AND status = 'pending' "
                "AND redacted_at IS NULL",
                (now, rel_id),
            )
        return self.get(rel_id)

    def retract(self, rel_id: str, *, reason: str | None = None) -> Relationship:
        with self._writer_tx():
            now = self._utc_now()
            self.conn.execute(
                "UPDATE relationships SET status = 'retracted', retracted_at = ? "
                "WHERE relationship_id = ? AND redacted_at IS NULL",
                (now, rel_id),
            )
        return self.get(rel_id)

    def end_at(self, rel_id: str, *, ended_at: str) -> Relationship:
        """Mark a relationship as having ended on a specific date (bitemporal valid_until)."""
        with self._writer_tx():
            self.conn.execute(
                "UPDATE relationships SET ended_at = ? "
                "WHERE relationship_id = ? AND redacted_at IS NULL",
                (ended_at, rel_id),
            )
        return self.get(rel_id)

    def redact(self, rel_id: str, *, idempotency_id: str,
               reason: str | None = None) -> None:
        with self._writer_tx():
            now = self._utc_now()
            self.conn.execute(
                "UPDATE relationships SET status = 'retracted', redacted_at = ? "
                "WHERE relationship_id = ?",
                (now, rel_id),
            )

    # ── Read ────────────────────────────────────────────────────────

    def _row_to_relationship(self, row: tuple) -> Relationship:
        return Relationship(
            relationship_id=row[0], from_person_id=row[1], to_person_id=row[2],
            kind=row[3], label=row[4], started_at=row[5], ended_at=row[6],
            confidence=row[7], source=row[8], status=row[9], note=row[10],
            created_at=row[11], confirmed_at=row[12], retracted_at=row[13],
        )

    def get(self, rel_id: str) -> Relationship:
        row = self.conn.execute(
            "SELECT relationship_id, from_person_id, to_person_id, kind, label, "
            "started_at, ended_at, confidence, source, status, note, "
            "created_at, confirmed_at, retracted_at FROM relationships "
            "WHERE relationship_id = ? AND redacted_at IS NULL",
            (rel_id,),
        ).fetchone()
        if row is None:
            raise RelationshipNotFoundError(f"relationship not found: {rel_id}")
        return self._row_to_relationship(row)

    def neighbours_of(
        self,
        person_id: str,
        *,
        kind: str | None = None,
        active_only: bool = True,
    ) -> list[Relationship]:
        """All relationships touching this person."""
        clauses = ["(from_person_id = ? OR to_person_id = ?)", "redacted_at IS NULL"]
        params: list = [person_id, person_id]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if active_only:
            clauses.append("status = 'confirmed'")
            clauses.append("ended_at IS NULL")
        sql = (
            "SELECT relationship_id, from_person_id, to_person_id, kind, label, "
            "started_at, ended_at, confidence, source, status, note, "
            "created_at, confirmed_at, retracted_at FROM relationships WHERE "
            + " AND ".join(clauses)
        )
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_relationship(r) for r in rows]

    def shortest_path(
        self,
        from_person_id: str,
        to_person_id: str,
        *,
        max_depth: int = 6,
    ) -> list[str] | None:
        """BFS shortest path between two people through active relationships.

        Returns a list of person_ids from start to end, or None if no
        path exists within max_depth. Uses only confirmed, non-ended,
        non-redacted edges.
        """
        if from_person_id == to_person_id:
            return [from_person_id]
        # Build adjacency from confirmed active edges
        rows = self.conn.execute(
            "SELECT from_person_id, to_person_id FROM relationships "
            "WHERE status = 'confirmed' AND ended_at IS NULL "
            "AND redacted_at IS NULL"
        ).fetchall()
        adj: dict[str, set[str]] = defaultdict(set)
        for a, b in rows:
            adj[a].add(b)
            adj[b].add(a)
        # BFS
        visited = {from_person_id}
        queue = deque([(from_person_id, [from_person_id])])
        while queue:
            current, path = queue.popleft()
            # Number of edges traversed to reach `current` is len(path) - 1.
            # If we've already hit the depth cap, do not explore further.
            if (len(path) - 1) >= max_depth:
                continue
            for nxt in adj.get(current, ()):
                if nxt in visited:
                    continue
                new_path = path + [nxt]
                if nxt == to_person_id:
                    return new_path
                visited.add(nxt)
                queue.append((nxt, new_path))
        return None

    def list_kinds_for(self, person_id: str) -> dict[str, int]:
        """Count of each relationship kind this person has."""
        rows = self.conn.execute(
            "SELECT kind, COUNT(*) FROM relationships "
            "WHERE (from_person_id = ? OR to_person_id = ?) "
            "AND status = 'confirmed' AND redacted_at IS NULL "
            "GROUP BY kind",
            (person_id, person_id),
        ).fetchall()
        return {k: n for k, n in rows}

    def audit(self) -> RelationshipsAudit:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM relationships "
            "WHERE redacted_at IS NULL GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        total = sum(by_status.values())
        self_ref = self.conn.execute(
            "SELECT COUNT(*) FROM relationships "
            "WHERE from_person_id = to_person_id"
        ).fetchone()[0]
        # Dangling: refers to a person_id that doesn't exist in people
        dangling = 0
        try:
            dangling = self.conn.execute(
                """
                SELECT COUNT(*) FROM relationships r
                WHERE r.redacted_at IS NULL AND (
                    NOT EXISTS (SELECT 1 FROM people WHERE person_id = r.from_person_id)
                    OR
                    NOT EXISTS (SELECT 1 FROM people WHERE person_id = r.to_person_id)
                )
                """
            ).fetchone()[0]
        except sqlite3.OperationalError:
            # people table not present in this connection (e.g. shard); skip
            pass
        return RelationshipsAudit(
            total=total,
            confirmed=by_status.get("confirmed", 0),
            pending=by_status.get("pending", 0),
            retracted=by_status.get("retracted", 0),
            self_referential=self_ref,
            dangling=dangling,
        )


register_channel(RelationshipsChannel)


__all__ = [
    "RelationshipsChannel", "Relationship", "RelationshipsAudit",
    "RelationshipNotFoundError",
    "VALID_KINDS", "INVERSE_KIND", "SYMMETRIC_KINDS",
    "ensure_relationships_schema",
]
