"""
feedback/feedback.py — operator feedback system
v0.2.40 wholeness

Lets Kevin (and any future operator) rate workflow outcomes. Feedback
is stored alongside the workflow record in the ErebloStore, queryable
later for analysis and (eventually) for informing intent maturity
scoring with real history.

This is the simplest useful version: a thumbs-up/thumbs-down + optional
note. Future expansions (sentiment classification, automatic prompt
adjustments based on feedback patterns) compose on top, but the
foundation is just: persist the rating, link it to the workflow.

Schema (added to ErebloStore via migration):

    CREATE TABLE IF NOT EXISTS feedback (
        feedback_id TEXT PRIMARY KEY,
        workflow_id TEXT,         -- the task this feedback is about
        rating TEXT NOT NULL,     -- 'positive' | 'negative' | 'neutral'
        note TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (workflow_id) REFERENCES tasks(task_id)
    );
"""
from __future__ import annotations

import json
import sqlite3


def _connect(path) -> sqlite3.Connection:  # db-armor-d
    """One hardened connect for every feedback DB access — the same
    pragma block atoms.db/events.db carry (db.py), so a concurrent
    cockpit + CLI can't throw 'database is locked' here."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

try:
    from ulid import ULID
except ImportError:
    import uuid
    def ULID():
        return uuid.uuid4().hex.upper()


Rating = Literal["positive", "negative", "neutral"]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class FeedbackRecord:
    feedback_id: str
    workflow_id: str
    rating: Rating
    note: str = ""
    created_at: str = field(default_factory=_iso_now)


class FeedbackManager:
    """Stores and retrieves operator feedback on workflows.

    Takes an ErebloStore at construction. Uses the same SQLite
    connection conventions as the rest of persistence/.
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS feedback (
        feedback_id TEXT PRIMARY KEY,
        workflow_id TEXT,
        rating TEXT NOT NULL,
        note TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_feedback_workflow ON feedback(workflow_id);
    CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);
    """

    def __init__(self, store):
        self._store = store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the feedback table if it doesn't exist."""
        conn = _connect(self._store._path)
        try:
            conn.executescript(self.SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def record(
        self,
        workflow_id: str,
        rating: Rating,
        note: str = "",
    ) -> str:
        """Record feedback. Returns the feedback_id."""
        feedback_id = str(ULID())
        conn = _connect(self._store._path)
        try:
            conn.execute(
                "INSERT INTO feedback (feedback_id, workflow_id, rating, note, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (feedback_id, workflow_id, rating, note, _iso_now()),
            )
            conn.commit()
        finally:
            conn.close()
        return feedback_id

    def list_for_workflow(self, workflow_id: str) -> list[FeedbackRecord]:
        """Return all feedback records for one workflow."""
        conn = _connect(self._store._path)
        try:
            rows = conn.execute(
                "SELECT feedback_id, workflow_id, rating, note, created_at "
                "FROM feedback WHERE workflow_id = ? ORDER BY created_at",
                (workflow_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            FeedbackRecord(
                feedback_id=r[0], workflow_id=r[1], rating=r[2],
                note=r[3] or "", created_at=r[4],
            )
            for r in rows
        ]

    def summary_for_workflow(self, workflow_id: str) -> dict:
        """Aggregate feedback summary for one workflow."""
        records = self.list_for_workflow(workflow_id)
        return {
            "workflow_id": workflow_id,
            "total": len(records),
            "positive": sum(1 for r in records if r.rating == "positive"),
            "negative": sum(1 for r in records if r.rating == "negative"),
            "neutral": sum(1 for r in records if r.rating == "neutral"),
            "notes": [r.note for r in records if r.note],
        }

    def overall_stats(self) -> dict:
        """Aggregate stats across all feedback."""
        conn = _connect(self._store._path)
        try:
            rows = conn.execute(
                "SELECT rating, COUNT(*) FROM feedback GROUP BY rating"
            ).fetchall()
        finally:
            conn.close()
        stats = {"positive": 0, "negative": 0, "neutral": 0}
        for rating, count in rows:
            if rating in stats:
                stats[rating] = count
        stats["total"] = sum(stats.values())
        return stats


__all__ = ["FeedbackManager", "FeedbackRecord", "Rating"]
