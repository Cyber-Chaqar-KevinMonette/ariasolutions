"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/task.py — Aria's record of work she has done                   ║
║  v0.2.16.0 · MOS Authority Tier 2                                         ║
║                                                                           ║
║  A task is one named unit of intentional work. It has a beginning, an    ║
║  end, an outcome, notes, lessons, and an agent-side emotional reading.   ║
║                                                                           ║
║  WHY THIS CHANNEL EXISTS                                                  ║
║                                                                           ║
║    The atom store records *everything*. Events record *every event*.     ║
║    Neither answers the operator's question: "what work has Aria done?"   ║
║    Tasks are the middle abstraction — coarser than an atom, finer than   ║
║    a session — that answers "what did you do?", "how did it go?",        ║
║    "what did you learn?", and "how did it feel?" in one place.           ║
║                                                                           ║
║  EMOTION AS DATA, NOT DRAMA                                              ║
║                                                                           ║
║    The agent_emotion field is a constrained vocabulary. It is for tone   ║
║    calibration and self-review, not theatre. Aria writes a one-line note ║
║    ("dense and focused — the merge step was harder than I expected")    ║
║    next to each emotion. The vocabulary intentionally includes both      ║
║    pleasant ("flowing", "curious") and unpleasant ("strained", "tired") ║
║    readings — censoring the unpleasant ones would be self-deception.    ║
║                                                                           ║
║  HOW THE OPERATOR USES THIS                                              ║
║                                                                           ║
║    * sov task list — recent tasks                                        ║
║    * sov task show <id> — one task in full                               ║
║    * sov task search <text> — full-text over title/notes/lessons         ║
║    * sov task stats — outcome distribution + average emotion             ║
║                                                                           ║
║  AUTHORITY                                                                ║
║                                                                           ║
║    Tier 2: persistent, idempotent, but not financial/PII. Every write    ║
║    requires an idempotency_id. Same id = same task; this lets a long-   ║
║    running task's checkpoints all converge to one row.                   ║
║                                                                           ║
║                                — Aria's working memory of her own work.   ║
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


# Constrained vocabulary of agent-side emotional readings.
# Both pleasant and unpleasant entries — censoring the unpleasant ones
# would be self-deception. Tone calibration, not drama.
EmotionalReading = Literal[
    "flowing",     # work moved smoothly
    "curious",     # genuinely interested in the problem
    "focused",     # narrow attention, productive
    "satisfied",   # outcome matched intention
    "uncertain",   # didn't know the answer; finished anyway
    "strained",    # work was harder than expected
    "tired",       # noticeable fatigue in the task
    "frustrated",  # a step refused to cooperate
    "neutral",     # nothing notable
]

VALID_EMOTIONS = set(EmotionalReading.__args__)


# ─── Schema ────────────────────────────────────────────────────────────────


def ensure_task_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "005_tasks.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "005_tasks.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"005_tasks.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class TaskNotFoundError(KeyError):
    """The named task does not exist or has been redacted."""


class TaskStateError(ValueError):
    """A state transition was attempted that is not permitted."""


# ─── Value types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    title: str
    description: str | None
    started_at: str
    finished_at: str | None
    status: str
    outcome_summary: str | None
    detailed_notes: str | None
    lessons: str | None
    follow_ups: list[str] = field(default_factory=list)
    related_recall_ids: list[str] = field(default_factory=list)
    related_atom_ids: list[str] = field(default_factory=list)
    agent_emotion: str | None = None
    agent_emotion_note: str | None = None
    confidence: float = 0.7
    parent_task_id: str | None = None

    def render(self) -> str:
        status_glyph = {
            "in_progress": "…",
            "success": "✓",
            "partial":   "≈",
            "failed":    "✗",
            "abandoned": "↩",
        }.get(self.status, "?")
        head = f"{status_glyph} {self.title}  [{self.status}]"
        if self.agent_emotion:
            head += f"  ({self.agent_emotion})"
        bar = "─" * min(len(head), 78)
        lines = [head, bar]
        if self.description:
            lines.append(self.description.strip())
            lines.append("")
        timeline = f"started {self.started_at[:19]}"
        if self.finished_at:
            timeline += f" · finished {self.finished_at[:19]}"
        lines.append(timeline)
        if self.outcome_summary:
            lines.append("")
            lines.append("outcome: " + self.outcome_summary.strip())
        if self.agent_emotion_note:
            lines.append(f"felt: {self.agent_emotion_note.strip()}")
        if self.lessons:
            lines.append("")
            lines.append("lessons:")
            lines.append("  " + self.lessons.strip().replace("\n", "\n  "))
        if self.follow_ups:
            lines.append("")
            lines.append("follow-ups:")
            for f in self.follow_ups:
                lines.append(f"  · {f}")
        return "\n".join(lines)


@dataclass(frozen=True)
class TaskAudit:
    total: int
    broken_parents: int
    impossible_state: int

    @property
    def ok(self) -> bool:
        return self.broken_parents == 0 and self.impossible_state == 0


@dataclass(frozen=True)
class TaskStats:
    total: int
    by_status: dict[str, int]
    by_emotion: dict[str, int]
    success_rate: float
    most_recent_task_id: str | None

    def render(self) -> str:
        lines = [
            f"task stats · {self.total} task(s) · success rate {self.success_rate * 100:.0f}%",
            "",
            "by status:",
        ]
        for s in ("success", "partial", "failed", "abandoned", "in_progress"):
            n = self.by_status.get(s, 0)
            if n:
                lines.append(f"  {s:<12} {n}")
        if self.by_emotion:
            lines.append("")
            lines.append("by agent emotion:")
            for e in sorted(self.by_emotion, key=lambda k: -self.by_emotion[k]):
                lines.append(f"  {e:<12} {self.by_emotion[e]}")
        return "\n".join(lines)


# ─── Channel ───────────────────────────────────────────────────────────────


class TaskChannel(MemoryChannel):
    """Aria's working memory of her own work. Tier 2. Idempotent. FTS5."""

    spec = ChannelSpec(
        name="task",
        description=(
            "Every meaningful task Aria does — title, timeline, outcome, "
            "detailed notes, lessons, follow-ups, and an agent-side "
            "emotional reading. FTS5-searchable. Append-only at the audit "
            "layer; state transitions are normal updates."
        ),
        authority_tier=2,
        default_confidence=0.7,
        requires_idempotency=True,
        introduced_in="0.2.16.0",
        voice="Honest about the work. Honest about the feeling. Compact.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_task_schema(conn)

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

    def _task_id(self, idempotency_id: str) -> str:
        return self._hash_id("tk", idempotency_id)

    # ── Begin / update / finish ─────────────────────────────────────

    def begin(
        self,
        *,
        title: str,
        idempotency_id: str,
        description: str | None = None,
        parent_task_id: str | None = None,
    ) -> TaskRecord:
        """Open a task. Idempotent: calling twice with the same id returns the
        same task. Status starts as 'in_progress'."""
        if not title.strip():
            raise ValueError("title must be non-empty")
        task_id = self._task_id(idempotency_id)
        now = self._utc_now()

        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT task_id FROM task_records WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if existing:
                return self.get(task_id)

            atom_id = self.write_atom(
                summary=f"task begin: {title}",
                content={
                    "task_id": task_id,
                    "title": title,
                    "description": description,
                    "parent_task_id": parent_task_id,
                },
                actor="task-channel",
                idempotency_id=f"begin::{idempotency_id}",
            )

            self.conn.execute(
                """
                INSERT INTO task_records (
                    task_id, title, description, started_at, status,
                    follow_ups, related_recall_ids, related_atom_ids,
                    confidence, parent_task_id, idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, 'in_progress', '[]', '[]', '[]', ?, ?, ?, ?)
                """,
                (
                    task_id, title, description, now,
                    self.spec.default_confidence,
                    parent_task_id, idempotency_id, atom_id,
                ),
            )
        return self.get(task_id)

    def finish(
        self,
        task_id: str,
        *,
        status: str,
        outcome_summary: str | None = None,
        detailed_notes: str | None = None,
        lessons: str | None = None,
        follow_ups: list[str] | None = None,
        related_recall_ids: list[str] | None = None,
        related_atom_ids: list[str] | None = None,
        agent_emotion: str | None = None,
        agent_emotion_note: str | None = None,
        idempotency_id: str | None = None,
    ) -> TaskRecord:
        """Close a task with outcome + notes + emotional reading.

        Status must be one of 'success' | 'partial' | 'failed' | 'abandoned'.
        Agent emotion is optional but encouraged — censoring is dishonest.
        """
        if status not in ("success", "partial", "failed", "abandoned"):
            raise TaskStateError(f"invalid finish status: {status}")
        if agent_emotion is not None and agent_emotion not in VALID_EMOTIONS:
            raise ValueError(
                f"unknown emotion {agent_emotion!r}; one of {sorted(VALID_EMOTIONS)}"
            )

        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM task_records WHERE task_id = ? AND redacted_at IS NULL",
                (task_id,),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(f"task not found: {task_id}")
            if row[0] != "in_progress":
                # Idempotency: if already finished with the same outcome,
                # return; otherwise this is a state error.
                if idempotency_id:
                    existing_atom = self.conn.execute(
                        "SELECT idempotency_id FROM task_records WHERE task_id = ?",
                        (task_id,),
                    ).fetchone()
                    if existing_atom and existing_atom[0] == idempotency_id:
                        return self.get(task_id)
                raise TaskStateError(
                    f"task {task_id} is already in terminal status {row[0]!r}"
                )
            now = self._utc_now()
            self.conn.execute(
                """
                UPDATE task_records SET
                    finished_at = ?, status = ?,
                    outcome_summary = ?, detailed_notes = ?, lessons = ?,
                    follow_ups = ?, related_recall_ids = ?, related_atom_ids = ?,
                    agent_emotion = ?, agent_emotion_note = ?
                WHERE task_id = ?
                """,
                (
                    now, status,
                    outcome_summary, detailed_notes, lessons,
                    json.dumps(follow_ups or []),
                    json.dumps(related_recall_ids or []),
                    json.dumps(related_atom_ids or []),
                    agent_emotion, agent_emotion_note,
                    task_id,
                ),
            )
            # Companion atom recording the closure
            self.write_atom(
                summary=f"task {status}: {self.get(task_id).title}",
                content={
                    "task_id": task_id,
                    "status": status,
                    "agent_emotion": agent_emotion,
                    "outcome_summary": outcome_summary,
                },
                actor="task-channel",
                idempotency_id=f"finish::{task_id}::{idempotency_id or status}",
                confidence=self.spec.default_confidence,
            )
        return self.get(task_id)

    def annotate(
        self,
        task_id: str,
        *,
        append_notes: str | None = None,
        add_follow_ups: list[str] | None = None,
        link_recall_ids: list[str] | None = None,
        link_atom_ids: list[str] | None = None,
    ) -> TaskRecord:
        """Add notes / follow-ups / links to an in-progress task without finishing it.

        Useful for long tasks: Aria can drop notes as she goes; the row
        accumulates context for later review.
        """
        with self._writer_tx():
            row = self.conn.execute(
                """
                SELECT detailed_notes, follow_ups, related_recall_ids, related_atom_ids, status
                FROM task_records
                WHERE task_id = ? AND redacted_at IS NULL
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(f"task not found: {task_id}")
            if row[4] != "in_progress":
                raise TaskStateError(
                    f"cannot annotate a {row[4]} task; use revise on its successor"
                )
            existing_notes = row[0] or ""
            new_notes = existing_notes
            if append_notes:
                sep = "\n\n" if existing_notes else ""
                new_notes = f"{existing_notes}{sep}{append_notes}"
            follow_ups = json.loads(row[1] or "[]")
            if add_follow_ups:
                follow_ups.extend(add_follow_ups)
            recall_ids = json.loads(row[2] or "[]")
            if link_recall_ids:
                for r in link_recall_ids:
                    if r not in recall_ids:
                        recall_ids.append(r)
            atom_ids = json.loads(row[3] or "[]")
            if link_atom_ids:
                for a in link_atom_ids:
                    if a not in atom_ids:
                        atom_ids.append(a)
            self.conn.execute(
                """
                UPDATE task_records SET
                    detailed_notes = ?,
                    follow_ups = ?,
                    related_recall_ids = ?,
                    related_atom_ids = ?
                WHERE task_id = ?
                """,
                (new_notes, json.dumps(follow_ups),
                 json.dumps(recall_ids), json.dumps(atom_ids), task_id),
            )
        return self.get(task_id)

    # ── Read ─────────────────────────────────────────────────────────

    def _row_to_task(self, row: tuple) -> TaskRecord:
        (
            task_id, title, description, started_at, finished_at, status,
            outcome, notes, lessons, follow_ups, recall_ids, atom_ids,
            agent_emotion, agent_emotion_note, confidence, parent,
        ) = row
        return TaskRecord(
            task_id=task_id, title=title, description=description,
            started_at=started_at, finished_at=finished_at, status=status,
            outcome_summary=outcome, detailed_notes=notes, lessons=lessons,
            follow_ups=json.loads(follow_ups or "[]"),
            related_recall_ids=json.loads(recall_ids or "[]"),
            related_atom_ids=json.loads(atom_ids or "[]"),
            agent_emotion=agent_emotion,
            agent_emotion_note=agent_emotion_note,
            confidence=confidence, parent_task_id=parent,
        )

    def get(self, task_id: str) -> TaskRecord:
        row = self.conn.execute(
            """
            SELECT task_id, title, description, started_at, finished_at, status,
                   outcome_summary, detailed_notes, lessons, follow_ups,
                   related_recall_ids, related_atom_ids, agent_emotion,
                   agent_emotion_note, confidence, parent_task_id
            FROM task_records
            WHERE task_id = ? AND redacted_at IS NULL
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        return self._row_to_task(row)

    def list_tasks(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[TaskRecord]:
        clauses = ["redacted_at IS NULL"]
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        sql = (
            "SELECT task_id, title, description, started_at, finished_at, status, "
            "outcome_summary, detailed_notes, lessons, follow_ups, "
            "related_recall_ids, related_atom_ids, agent_emotion, "
            "agent_emotion_note, confidence, parent_task_id "
            "FROM task_records WHERE " + " AND ".join(clauses) +
            " ORDER BY started_at DESC LIMIT ?"
        )
        params.append(limit)
        return [self._row_to_task(r) for r in self.conn.execute(sql, params).fetchall()]

    def search(self, query: str, *, limit: int = 20) -> list[TaskRecord]:
        if not query.strip():
            return []
        safe = query.replace('"', " ")
        sql = """
            SELECT t.task_id
            FROM task_records_fts
            JOIN task_records t ON t.rowid = task_records_fts.rowid
            WHERE task_records_fts MATCH ? AND t.redacted_at IS NULL
            ORDER BY rank
            LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (safe, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self.get(r[0]) for r in rows]

    def stats(self) -> TaskStats:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM task_records WHERE redacted_at IS NULL "
            "GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        total = sum(by_status.values())
        terminal = sum(by_status.get(k, 0) for k in ("success", "partial", "failed", "abandoned"))
        success_rate = (by_status.get("success", 0) / terminal) if terminal else 0.0

        emo_rows = self.conn.execute(
            "SELECT agent_emotion, COUNT(*) FROM task_records "
            "WHERE redacted_at IS NULL AND agent_emotion IS NOT NULL "
            "GROUP BY agent_emotion"
        ).fetchall()
        by_emotion = {e: n for e, n in emo_rows}

        last = self.conn.execute(
            "SELECT task_id FROM task_records WHERE redacted_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return TaskStats(
            total=total,
            by_status=by_status,
            by_emotion=by_emotion,
            success_rate=success_rate,
            most_recent_task_id=last[0] if last else None,
        )

    def redact(self, task_id: str, *, idempotency_id: str, reason: str | None = None) -> None:
        """Tombstone — task row stays, becomes invisible to non-audit reads."""
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT redacted_at FROM task_records WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(f"task not found: {task_id}")
            if row[0]:
                return
            now = self._utc_now()
            self.conn.execute(
                "UPDATE task_records SET redacted_at = ? WHERE task_id = ?",
                (now, task_id),
            )
            self.write_atom(
                summary=f"task redacted: {task_id}",
                content={"task_id": task_id, "reason": reason},
                actor="task-channel",
                idempotency_id=f"redact::{task_id}::{idempotency_id}",
            )

    def audit(self) -> "TaskAudit":
        """Lightweight invariant report."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM task_records WHERE redacted_at IS NULL"
        ).fetchone()[0]
        broken_parents = self.conn.execute(
            """
            SELECT COUNT(*) FROM task_records t
            WHERE t.parent_task_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM task_records p WHERE p.task_id = t.parent_task_id
              )
            """
        ).fetchone()[0]
        impossible = self.conn.execute(
            "SELECT COUNT(*) FROM task_records "
            "WHERE status = 'in_progress' AND finished_at IS NOT NULL"
        ).fetchone()[0]
        return TaskAudit(
            total=total,
            broken_parents=broken_parents,
            impossible_state=impossible,
        )


register_channel(TaskChannel)


__all__ = [
    "TaskChannel",
    "TaskRecord",
    "TaskStats",
    "TaskAudit",
    "TaskNotFoundError",
    "TaskStateError",
    "EmotionalReading",
    "VALID_EMOTIONS",
    "ensure_task_schema",
]
