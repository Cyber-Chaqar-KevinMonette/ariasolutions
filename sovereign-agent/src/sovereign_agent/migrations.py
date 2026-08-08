"""
╔══════════════════════════════════════════════════════════════════════════╗
║  migrations.py — versioned, idempotent schema migrations                 ║
║  v0.2.18.0                                                                ║
║                                                                           ║
║  WHY THIS EXISTS                                                         ║
║                                                                           ║
║    Until now, each channel's ``ensure_<x>_schema()`` function ran on    ║
║    every connection open. SQL files were idempotent by convention      ║
║    (CREATE IF NOT EXISTS, ALTER TABLE wrapped in try/except). That    ║
║    worked, but it doesn't scale: we cannot tell which version of any  ║
║    schema a database is currently at, and rolling forward across      ║
║    many releases becomes a guessing game.                             ║
║                                                                           ║
║    Aria's home is going to outlive many releases of her own code.     ║
║    Schema migrations need to be first-class.                          ║
║                                                                           ║
║  HOW IT WORKS                                                            ║
║                                                                           ║
║    Each DB has a ``schema_migrations`` table:                          ║
║                                                                           ║
║      ('001_events',      '0.2.0',  '2025-...', 'applied')             ║
║      ('002_atoms',       '0.2.0',  '2025-...', 'applied')             ║
║      ('003_people',      '0.2.15', '2025-...', 'applied')             ║
║      ('004_recalls',     '0.2.16', '2026-...', 'applied')             ║
║      ('005_tasks',       '0.2.16', '2026-...', 'applied')             ║
║      ('006_rewards',     '0.2.16', '2026-...', 'applied')             ║
║      ('007_bitemporal',  '0.2.17', '2026-...', 'applied')             ║
║      ('008_episodes',    '0.2.17', '2026-...', 'applied')             ║
║      ('009_reasoning',   '0.2.18', '2026-...', 'applied')             ║
║      ('010_gaps',        '0.2.18', '2026-...', 'applied')             ║
║      ('011_relationships','0.2.18','2026-...', 'applied')             ║
║      ('012_commitments', '0.2.18', '2026-...', 'applied')             ║
║      ('013_heartbeat',   '0.2.18', '2026-...', 'applied')             ║
║      ('014_archive',     '0.2.18', '2026-...', 'applied')             ║
║                                                                           ║
║    The ``apply_pending(conn)`` function iterates every registered      ║
║    migration in order, skipping ones already in the table, and        ║
║    applying ones that aren't. Each migration is a (name, version,     ║
║    sql_string_or_callable) tuple.                                     ║
║                                                                           ║
║  IDEMPOTENCY DISCIPLINE                                                  ║
║                                                                           ║
║    Migrations should still BE idempotent (CREATE IF NOT EXISTS etc.)   ║
║    as defense in depth. The framework just makes "have we run this    ║
║    yet?" a first-class fact instead of a SQL-level guess.             ║
║                                                                           ║
║                                — schema time, named, dated, auditable.   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Union


# A migration is either an SQL string OR a callable that takes a conn.
# Callables are for migrations that need Python logic (e.g. data backfill).
MigrationBody = Union[str, Callable[[sqlite3.Connection], None]]


@dataclass(frozen=True)
class Migration:
    name: str            # e.g. "004_recalls"
    version: str         # release version this was introduced in
    body: MigrationBody  # SQL or callable
    notes: str = ""      # short description for audit


# ─── Migration registry ────────────────────────────────────────────────────


_MIGRATIONS: list[Migration] = []


def register(migration: Migration) -> None:
    """Add a migration to the global registry. Idempotent on name."""
    for existing in _MIGRATIONS:
        if existing.name == migration.name:
            return
    _MIGRATIONS.append(migration)


def get_registered() -> list[Migration]:
    """Return registered migrations in registration order."""
    return list(_MIGRATIONS)


def reset_registry() -> None:
    """Test helper: clear the registry."""
    _MIGRATIONS.clear()


# ─── Schema table bootstrap ───────────────────────────────────────────────


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name        TEXT PRIMARY KEY,
            version     TEXT NOT NULL,
            applied_at  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'applied',
            notes       TEXT,
            checksum    TEXT
        ) STRICT
        """
    )
    conn.commit()


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    """Return the set of migration names that have already been applied."""
    ensure_migrations_table(conn)
    rows = conn.execute(
        "SELECT name FROM schema_migrations WHERE status = 'applied'"
    ).fetchall()
    return {r[0] for r in rows}


# ─── Applying migrations ──────────────────────────────────────────────────


def apply_pending(
    conn: sqlite3.Connection,
    *,
    only: list[str] | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Apply all registered migrations that haven't been applied yet.

    Returns the list of newly-applied migration names (in order).
    If ``only`` is given, restricts to those names.
    If ``dry_run`` is True, returns what *would* be applied without
    modifying the database.

    Each migration runs in its own transaction. Failure of one
    migration does not roll back previously-successful ones; it raises
    and leaves the DB at the last successfully-applied migration.
    """
    ensure_migrations_table(conn)
    applied = applied_migrations(conn)
    newly: list[str] = []

    for mig in _MIGRATIONS:
        if mig.name in applied:
            continue
        if only is not None and mig.name not in only:
            continue
        if dry_run:
            newly.append(mig.name)
            continue
        # Apply
        was_in_tx = conn.in_transaction
        if not was_in_tx:
            conn.execute("BEGIN IMMEDIATE")
        try:
            if isinstance(mig.body, str):
                conn.executescript(mig.body)
            elif callable(mig.body):
                mig.body(conn)
            else:
                raise TypeError(f"unknown migration body type: {type(mig.body)}")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            conn.execute(
                "INSERT INTO schema_migrations (name, version, applied_at, "
                "status, notes) VALUES (?, ?, ?, 'applied', ?)",
                (mig.name, mig.version, now, mig.notes),
            )
            if not was_in_tx:
                conn.commit()
            newly.append(mig.name)
        except Exception:
            if not was_in_tx:
                conn.rollback()
            raise

    return newly


def status(conn: sqlite3.Connection) -> list[dict]:
    """Report the status of every registered migration against this DB."""
    applied = applied_migrations(conn)
    return [
        {
            "name": m.name,
            "version": m.version,
            "status": "applied" if m.name in applied else "pending",
            "notes": m.notes,
        }
        for m in _MIGRATIONS
    ]


# ─── Helpers for SQL-file-backed migrations ──────────────────────────────


def from_sql_file(path: Path) -> str:
    """Read a .sql file and return its contents as a migration body."""
    return path.read_text(encoding="utf-8")


# ─── Backfill detection ───────────────────────────────────────────────────


# Map of migration name → tables/objects whose existence proves it was applied.
# Used by ``backfill_applied()`` so that an existing database upgraded from a
# pre-migration-framework version doesn't try to re-run migrations whose
# schema is already present.
_SCHEMA_FINGERPRINTS: dict[str, list[str]] = {
    "001_events":         ["events"],
    "002_atoms":          ["atoms"],
    "003_people":         ["people", "people_aliases", "people_facts"],
    "004_recalls":        ["recalls", "recall_sources"],
    "005_tasks":          ["task_records"],
    "006_rewards":        ["rewards"],
    "007_bitemporal":     [],   # column-add migration; detected via PRAGMA below
    "008_episodes":       ["episodes", "episode_members"],
    "009_reasoning":      ["reasoning_traces", "reasoning_steps"],
    "010_gaps":           ["knowledge_gaps"],
    "011_relationships":  ["relationships"],
    "012_commitments":    ["commitments"],
    "013_heartbeat":      ["heartbeats"],
    "014_archive":        ["archive", "archive_refs"],
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(r[1] == column for r in rows)


def detect_applied(
    conn: sqlite3.Connection,
    *,
    fingerprints: dict[str, list[str]] | None = None,
) -> set[str]:
    """Heuristic: which migrations are 'already applied' based on schema?

    Used by ``backfill_applied`` to populate ``schema_migrations`` for
    databases that pre-date the migration framework. A migration's
    schema is considered present iff every fingerprint table exists.

    The bitemporal migration (007) is a special case: it adds columns
    to existing tables rather than creating new ones, so we check for
    the ``valid_from`` column on ``people_facts``.
    """
    fp = fingerprints if fingerprints is not None else _SCHEMA_FINGERPRINTS
    out: set[str] = set()
    for name, tables in fp.items():
        if not tables:
            # Column-add migration. Special-case 007 by name.
            if name == "007_bitemporal":
                if (_column_exists(conn, "people_facts", "valid_from")
                        and _column_exists(conn, "recalls", "valid_from")):
                    out.add(name)
            continue
        if all(_table_exists(conn, t) for t in tables):
            out.add(name)
    return out


def backfill_applied(
    conn: sqlite3.Connection,
    *,
    fingerprints: dict[str, list[str]] | None = None,
    version: str = "backfilled",
) -> list[str]:
    """For every registered migration whose schema is ALREADY present, mark it
    applied in ``schema_migrations`` without re-running its body.

    Returns the list of migration names that were backfilled. This is the
    safe upgrade path for databases that were created before the migration
    framework existed (v0.2.x prior to 0.2.18.0).

    Call this BEFORE ``apply_pending``. The flow is:

        ensure_migrations_table(conn)
        backfill_applied(conn)      # mark anything whose tables exist
        apply_pending(conn)         # run only true new migrations
    """
    ensure_migrations_table(conn)
    already_recorded = applied_migrations(conn)
    detected = detect_applied(conn, fingerprints=fingerprints)
    backfilled: list[str] = []
    for name in detected:
        if name in already_recorded:
            continue
        # Look up the migration record for the version string
        mig_version = version
        for m in _MIGRATIONS:
            if m.name == name:
                mig_version = m.version
                break
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn.execute(
            "INSERT INTO schema_migrations (name, version, applied_at, "
            "status, notes) VALUES (?, ?, ?, 'applied', ?)",
            (name, mig_version, now,
             "backfilled: schema fingerprint detected on existing DB"),
        )
        backfilled.append(name)
    conn.commit()
    return backfilled


def register_sql_dir(sql_dir: Path, version: str = "0.2.18.0") -> int:
    """Register every .sql file in a directory as a migration.

    File name (without .sql) becomes the migration name. Useful for
    bootstrapping the registry from the existing sql/ folder. Returns
    the count registered.
    """
    if not sql_dir.is_dir():
        return 0
    count = 0
    for f in sorted(sql_dir.glob("*.sql")):
        name = f.stem
        body = from_sql_file(f)
        register(Migration(name=name, version=version, body=body,
                            notes=f"auto-registered from {f.name}"))
        count += 1
    return count


__all__ = [
    "Migration", "MigrationBody",
    "register", "get_registered", "reset_registry",
    "ensure_migrations_table", "applied_migrations",
    "apply_pending", "status",
    "from_sql_file", "register_sql_dir",
    "detect_applied", "backfill_applied",
]
