"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/episodes.py — coherent spans of Aria's activity                ║
║  v0.2.17.0 · MOS Authority Tier 1                                         ║
║                                                                           ║
║  WHY THIS CHANNEL EXISTS                                                 ║
║                                                                           ║
║    Cognitive science distinguishes episodic memory (what happened, in   ║
║    coherent sessions) from semantic memory (decontextualised facts).    ║
║    Aria already has both atoms (semantic-leaning leaves) and tasks      ║
║    (named work units). What she lacks is the *binding* layer: the      ║
║    sense that "the Wednesday afternoon we worked on the merge logic"   ║
║    is ONE thing, with ONE beginning, middle, and end, that contains    ║
║    three tasks, two recalls, six atoms, and the conversation that      ║
║    framed all of them.                                                  ║
║                                                                           ║
║    Episodes are that binding layer. They:                              ║
║                                                                           ║
║      • Have a beginning, middle, and end (timestamps + status).        ║
║      • Hold a title and a summary written at close time.               ║
║      • Have a significance grade: routine / notable / landmark.        ║
║      • Group member artifacts via weak refs (kind, id pairs).          ║
║      • Can nest (a long campaign contains multiple sessions).          ║
║      • Are FTS5-searchable on title + description + summary.           ║
║                                                                           ║
║  AUTHORITY                                                               ║
║                                                                           ║
║    Tier 1: light, idempotent, observational. The operator (or future   ║
║    automation in the dream-reflector) opens an episode, adds members   ║
║    while work happens, and closes the episode with a summary when     ║
║    the work ends.                                                       ║
║                                                                           ║
║                                — the binding layer of Aria's memory.    ║
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
from typing import Iterator

from ..channels import ChannelSpec, MemoryChannel, register_channel


VALID_MEMBER_KINDS = frozenset({
    "atom", "task", "recall", "person", "fact", "reward",
})


# ─── Schema ────────────────────────────────────────────────────────────────


def ensure_episodes_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "008_episodes.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "008_episodes.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"008_episodes.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class EpisodeNotFoundError(KeyError):
    """The named episode does not exist or has been redacted."""


class EpisodeStateError(ValueError):
    """A state transition was attempted that is not permitted."""


# ─── Types ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EpisodeMember:
    member_id: str
    episode_id: str
    member_kind: str
    member_ref: str
    role: str | None
    note: str | None
    added_at: str


@dataclass(frozen=True)
class Episode:
    episode_id: str
    title: str
    description: str | None
    started_at: str
    closed_at: str | None
    archived_at: str | None
    status: str
    summary: str | None
    significance: int
    tags: list[str] = field(default_factory=list)
    parent_episode_id: str | None = None
    members: list[EpisodeMember] = field(default_factory=list)

    def render(self) -> str:
        glyph = {
            "open":     "◯",
            "closed":   "●",
            "archived": "▢",
            "redacted": "▨",
        }.get(self.status, "?")
        sig = {1: "routine", 2: "notable", 3: "landmark"}.get(self.significance, "?")
        head = f"{glyph}  {self.title}  [{self.status} · {sig}]"
        bar = "─" * min(72, len(head))
        lines = [head, bar]
        if self.description:
            lines.append(self.description.strip())
            lines.append("")
        timeline = f"started {self.started_at[:19]}"
        if self.closed_at:
            timeline += f" · closed {self.closed_at[:19]}"
        lines.append(timeline)
        if self.summary:
            lines.append("")
            lines.append("summary: " + self.summary.strip())
        if self.tags:
            lines.append("")
            lines.append("tags: " + ", ".join(self.tags))
        if self.members:
            lines.append("")
            lines.append(f"members ({len(self.members)}):")
            for m in self.members[:20]:
                role = f" [{m.role}]" if m.role else ""
                lines.append(f"  · {m.member_kind} {m.member_ref}{role}")
            if len(self.members) > 20:
                lines.append(f"  … and {len(self.members) - 20} more")
        return "\n".join(lines)


@dataclass(frozen=True)
class EpisodeAudit:
    total: int
    open: int
    closed: int
    archived: int
    dangling_members: int
    long_open: int           # open > 30 days

    @property
    def ok(self) -> bool:
        return self.dangling_members == 0


# ─── Channel ──────────────────────────────────────────────────────────────


class EpisodesChannel(MemoryChannel):
    """Coherent spans of activity. Tier 1. Idempotent. FTS5-searchable."""

    spec = ChannelSpec(
        name="episodes",
        description=(
            "Named, time-bounded sessions of activity. Group atoms, tasks, "
            "recalls, and people into coherent narratives the operator can "
            "refer to. Episodes have a beginning, middle, end; a summary "
            "written at close; and a significance grade."
        ),
        authority_tier=1,
        default_confidence=0.8,
        requires_idempotency=True,
        introduced_in="0.2.17.0",
        voice="Narrative, dated, bounded. Names the arc so it can be remembered.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_episodes_schema(conn)

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
        significance: int = 1,
        tags: list[str] | None = None,
        parent_episode_id: str | None = None,
    ) -> Episode:
        """Begin a new episode. Idempotent."""
        if not title.strip():
            raise ValueError("title must be non-empty")
        if significance not in (1, 2, 3):
            raise ValueError("significance must be 1, 2, or 3")
        episode_id = self._hash_id("ep", idempotency_id)
        now = self._utc_now()
        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT episode_id FROM episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            if existing:
                return self.get(episode_id)
            atom_id = self.write_atom(
                summary=f"episode opened: {title}",
                content={"episode_id": episode_id, "title": title,
                          "parent_episode_id": parent_episode_id,
                          "significance": significance},
                actor="episodes-channel",
                idempotency_id=idempotency_id,
                confidence=self.spec.default_confidence,
            )
            self.conn.execute(
                """
                INSERT INTO episodes (
                    episode_id, title, description, started_at, status,
                    significance, tags, parent_episode_id, idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
                """,
                (
                    episode_id, title, description, now, significance,
                    json.dumps(tags or []), parent_episode_id,
                    idempotency_id, atom_id,
                ),
            )
        return self.get(episode_id)

    # ── Membership ──────────────────────────────────────────────────

    def add_member(
        self,
        episode_id: str,
        *,
        member_kind: str,
        member_ref: str,
        role: str | None = None,
        note: str | None = None,
    ) -> EpisodeMember:
        """Attach an artifact to the episode."""
        if member_kind not in VALID_MEMBER_KINDS:
            raise ValueError(f"unknown member_kind {member_kind!r}; "
                             f"one of {sorted(VALID_MEMBER_KINDS)}")
        if not member_ref.strip():
            raise ValueError("member_ref must be non-empty")
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            if row is None:
                raise EpisodeNotFoundError(f"episode not found: {episode_id}")
            if row[0] == "redacted":
                raise EpisodeStateError("cannot add member to redacted episode")
            now = self._utc_now()
            member_id = self._hash_id(
                "em", f"{episode_id}::{member_kind}::{member_ref}"
            )
            self.conn.execute(
                """
                INSERT OR IGNORE INTO episode_members (
                    member_id, episode_id, member_kind, member_ref,
                    role, note, added_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (member_id, episode_id, member_kind, member_ref, role, note, now),
            )
            mrow = self.conn.execute(
                "SELECT member_id, episode_id, member_kind, member_ref, "
                "role, note, added_at FROM episode_members WHERE member_id = ?",
                (member_id,),
            ).fetchone()
            return EpisodeMember(*mrow)

    # ── Close / archive ─────────────────────────────────────────────

    def close(
        self,
        episode_id: str,
        *,
        summary: str | None = None,
        idempotency_id: str | None = None,
    ) -> Episode:
        """Close an open episode. Writes summary if provided."""
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM episodes WHERE episode_id = ? "
                "AND redacted_at IS NULL",
                (episode_id,),
            ).fetchone()
            if row is None:
                raise EpisodeNotFoundError(f"episode not found: {episode_id}")
            if row[0] != "open":
                # Idempotent: closing a closed episode is a no-op if same summary
                return self.get(episode_id)
            now = self._utc_now()
            self.conn.execute(
                "UPDATE episodes SET status = 'closed', closed_at = ?, "
                "summary = COALESCE(?, summary) WHERE episode_id = ?",
                (now, summary, episode_id),
            )
            self.write_atom(
                summary=f"episode closed: {self.get(episode_id).title}",
                content={"episode_id": episode_id, "transition": "closed"},
                actor="episodes-channel",
                idempotency_id=f"close::{episode_id}::{idempotency_id or now}",
                confidence=self.spec.default_confidence,
            )
        return self.get(episode_id)

    def archive(self, episode_id: str) -> Episode:
        """Soft 'put away' — episode stays readable but is excluded from default lists."""
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM episodes WHERE episode_id = ? "
                "AND redacted_at IS NULL",
                (episode_id,),
            ).fetchone()
            if row is None:
                raise EpisodeNotFoundError(f"episode not found: {episode_id}")
            if row[0] not in ("closed", "archived"):
                raise EpisodeStateError(
                    f"cannot archive an episode in status {row[0]!r}; close it first"
                )
            now = self._utc_now()
            self.conn.execute(
                "UPDATE episodes SET status = 'archived', archived_at = ? "
                "WHERE episode_id = ?",
                (now, episode_id),
            )
        return self.get(episode_id)

    def redact(self, episode_id: str, *, idempotency_id: str,
               reason: str | None = None) -> None:
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT redacted_at FROM episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            if row is None:
                raise EpisodeNotFoundError(f"episode not found: {episode_id}")
            if row[0]:
                return
            now = self._utc_now()
            self.conn.execute(
                "UPDATE episodes SET status = 'redacted', redacted_at = ? "
                "WHERE episode_id = ?",
                (now, episode_id),
            )
            self.write_atom(
                summary=f"episode redacted: {episode_id}",
                content={"episode_id": episode_id, "reason": reason},
                actor="episodes-channel",
                idempotency_id=f"redact::{episode_id}::{idempotency_id}",
                confidence=self.spec.default_confidence,
            )

    # ── Read ─────────────────────────────────────────────────────────

    def _fetch_episode(self, episode_id: str, *, include_redacted: bool = False) -> Episode | None:
        row = self.conn.execute(
            """
            SELECT episode_id, title, description, started_at, closed_at,
                   archived_at, status, summary, significance, tags,
                   parent_episode_id
            FROM episodes WHERE episode_id = ?
            """,
            (episode_id,),
        ).fetchone()
        if row is None:
            return None
        (eid, title, desc, started, closed, archived, status, summary,
         sig, tags_json, parent) = row
        if status == "redacted" and not include_redacted:
            return None
        members_rows = self.conn.execute(
            """
            SELECT member_id, episode_id, member_kind, member_ref, role, note, added_at
            FROM episode_members WHERE episode_id = ?
            ORDER BY added_at
            """,
            (episode_id,),
        ).fetchall()
        members = [EpisodeMember(*r) for r in members_rows]
        return Episode(
            episode_id=eid, title=title, description=desc,
            started_at=started, closed_at=closed, archived_at=archived,
            status=status, summary=summary, significance=sig,
            tags=json.loads(tags_json or "[]"),
            parent_episode_id=parent, members=members,
        )

    def get(self, episode_id: str, *, include_redacted: bool = False) -> Episode:
        ep = self._fetch_episode(episode_id, include_redacted=include_redacted)
        if ep is None:
            raise EpisodeNotFoundError(f"episode not found or redacted: {episode_id}")
        return ep

    def list_episodes(
        self,
        *,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
    ) -> list[Episode]:
        clauses = ["redacted_at IS NULL"]
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        elif not include_archived:
            clauses.append("status != 'archived'")
        sql = (
            "SELECT episode_id FROM episodes WHERE " + " AND ".join(clauses) +
            " ORDER BY started_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self.get(r[0]) for r in rows]

    def search(self, query: str, *, limit: int = 20) -> list[Episode]:
        if not query.strip():
            return []
        safe = query.replace('"', " ")
        sql = """
            SELECT e.episode_id
            FROM episodes_fts
            JOIN episodes e ON e.rowid = episodes_fts.rowid
            WHERE episodes_fts MATCH ? AND e.redacted_at IS NULL
            ORDER BY rank
            LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (safe, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self.get(r[0]) for r in rows]

    def find_by_member(
        self, *, member_kind: str, member_ref: str
    ) -> list[Episode]:
        """All episodes that include the given member."""
        rows = self.conn.execute(
            """
            SELECT DISTINCT em.episode_id FROM episode_members em
            JOIN episodes e ON e.episode_id = em.episode_id
            WHERE em.member_kind = ? AND em.member_ref = ?
              AND e.redacted_at IS NULL
            ORDER BY em.added_at DESC
            """,
            (member_kind, member_ref),
        ).fetchall()
        return [self.get(r[0]) for r in rows]

    def audit(self) -> EpisodeAudit:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM episodes WHERE redacted_at IS NULL "
            "GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        total = sum(by_status.values())
        # dangling: members whose episode is redacted/missing
        dangling = self.conn.execute(
            """
            SELECT COUNT(*) FROM episode_members em
            LEFT JOIN episodes e ON e.episode_id = em.episode_id
            WHERE e.episode_id IS NULL OR e.redacted_at IS NOT NULL
            """
        ).fetchone()[0]
        # long-open: started > 30 days ago, still open
        long_open = self.conn.execute(
            """
            SELECT COUNT(*) FROM episodes
            WHERE status = 'open' AND redacted_at IS NULL
              AND started_at < datetime('now', '-30 days')
            """
        ).fetchone()[0]
        return EpisodeAudit(
            total=total,
            open=by_status.get("open", 0),
            closed=by_status.get("closed", 0),
            archived=by_status.get("archived", 0),
            dangling_members=dangling,
            long_open=long_open,
        )


register_channel(EpisodesChannel)


__all__ = [
    "EpisodesChannel", "Episode", "EpisodeMember", "EpisodeAudit",
    "EpisodeNotFoundError", "EpisodeStateError", "VALID_MEMBER_KINDS",
    "ensure_episodes_schema",
]
