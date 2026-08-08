"""
╔══════════════════════════════════════════════════════════════════════════╗
║  persistence/store.py — the durable store. The bones.                     ║
║  v0.2.37 — skeleton drop                                                  ║
║                                                                           ║
║  One SQLite database. Five tables. No magic.                              ║
║                                                                           ║
║    chats      — chat sessions as first-class objects                      ║
║    messages   — every turn, with chat_id + project_id + role + content    ║
║    projects   — project profiles + status                                 ║
║    tasks      — task graph entries owned by projects                      ║
║    timers     — scheduled work that survives restarts                     ║
║                                                                           ║
║  Why SQLite                                                              ║
║                                                                           ║
║    Boring, well-tested, ACID, zero ops. The agentic_loop needs           ║
║    transactions; SQLite gives them. The clock needs durability across     ║
║    restarts; SQLite gives that too. Postgres can come later if needed —  ║
║    the schema is portable.                                                ║
║                                                                           ║
║  Discipline                                                              ║
║                                                                           ║
║    Every table has created_at + updated_at. Every entity has a ULID id   ║
║    so insertion is monotonically time-ordered. WAL mode for concurrent    ║
║    reads. Foreign keys ON. No silent NULLs in primary fields.            ║
║                                                                           ║
║  Location: <data_dir>/erebo.db                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


SCHEMA_VERSION = 1


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Schema ──────────────────────────────────────────────────────────────


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id     TEXT PRIMARY KEY,       -- ULID
    title       TEXT NOT NULL,
    project_id  TEXT,                   -- nullable; chat may be unbound
    status      TEXT NOT NULL DEFAULT 'active', -- active|archived
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chats_status_updated
    ON chats(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chats_project ON chats(project_id);

CREATE TABLE IF NOT EXISTS messages (
    message_id  TEXT PRIMARY KEY,       -- ULID
    chat_id     TEXT NOT NULL,
    project_id  TEXT,
    role        TEXT NOT NULL,           -- user|assistant|system|tool
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '', -- comma-separated, lightweight
    created_at  TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_created
    ON messages(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id);

CREATE TABLE IF NOT EXISTS projects (
    project_id   TEXT PRIMARY KEY,      -- ULID
    name         TEXT UNIQUE NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    repo_path    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active', -- active|paused|archived
    profile_json TEXT NOT NULL DEFAULT '{}', -- free-form structured fields
    summary      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,      -- ULID
    project_id   TEXT NOT NULL,
    parent_task_id TEXT,                -- nullable; supports subtasks
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'planned',
                 -- planned|in_progress|done|blocked|abandoned
    ordinal      INTEGER NOT NULL DEFAULT 0,
    outcome_json TEXT NOT NULL DEFAULT '{}', -- what happened when executed
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_project_status
    ON tasks(project_id, status, ordinal);

CREATE TABLE IF NOT EXISTS timers (
    timer_id     TEXT PRIMARY KEY,      -- ULID
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,         -- one_shot|recurring|deadline
    fires_at     TEXT NOT NULL,         -- ISO; next fire time
    interval_sec INTEGER,               -- nullable; recurring only
    payload_json TEXT NOT NULL DEFAULT '{}', -- what to do when fired
    status       TEXT NOT NULL DEFAULT 'armed',
                 -- armed|fired|cancelled|done
    chat_id      TEXT,                  -- nullable; bind to a chat
    project_id   TEXT,                  -- nullable; bind to a project
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    last_fired_at TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE SET NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_timers_status_fires
    ON timers(status, fires_at);
"""


# ─── Store class ─────────────────────────────────────────────────────────


class ErebloStore:
    """The bones. A SQLite-backed durable store for chats, projects, tasks, timers.

    Construct once; share the instance across modules (sessions, projects,
    clock, workflow). Connection pooling is handled per-call.
    """

    def __init__(self, db_path: Path):
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init_db()

    @property
    def path(self) -> Path:
        return self._path

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            self._path, isolation_level="IMMEDIATE",
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.execute("PRAGMA busy_timeout = 5000")  # db-armor-d
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ─── Generic helpers (used by sessions/projects/clock/workflow) ──────

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._conn() as conn:
            conn.execute(sql, params)

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(sql, params).fetchall()

    # ─── Health / introspection ──────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        with self._conn() as conn:
            return {
                "chats": conn.execute(
                    "SELECT COUNT(*) FROM chats").fetchone()[0],
                "messages": conn.execute(
                    "SELECT COUNT(*) FROM messages").fetchone()[0],
                "projects": conn.execute(
                    "SELECT COUNT(*) FROM projects").fetchone()[0],
                "tasks": conn.execute(
                    "SELECT COUNT(*) FROM tasks").fetchone()[0],
                "timers_armed": conn.execute(
                    "SELECT COUNT(*) FROM timers WHERE status='armed'"
                ).fetchone()[0],
                "schema_version": int(
                    conn.execute(
                        "SELECT value FROM schema_meta WHERE key='schema_version'"
                    ).fetchone()[0]
                ),
            }


__all__ = ["ErebloStore", "SCHEMA_VERSION", "_iso_now"]
