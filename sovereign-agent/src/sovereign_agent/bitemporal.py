"""
sovereign_agent.bitemporal — two-time-dimension helpers for memory tables.

Bitemporal storage tracks two times per record:

    * system_time (when Aria wrote it)    — already present as created_at,
                                              superseded_at, etc.
    * valid_time  (when it was true)      — added by this module as
                                              valid_from, valid_until

Why: Aria can now honestly answer "what did I believe on date X?" by
filtering on system_time, AND "what was true on date X?" by filtering
on valid_time. The two questions have different answers; conflating
them is a common bug in audit systems.

This module is small. The point isn't a framework — it's a discipline.

Usage:

    add_bitemporal_columns(conn, "people_facts")
    add_bitemporal_columns(conn, "recalls")

Both are idempotent. They catch SQLite's "duplicate column" error and
swallow it. Indexes are CREATE IF NOT EXISTS so they're naturally safe.

Reading as-of:

    rows = as_of_filter(
        conn,
        sql="SELECT * FROM people_facts WHERE person_id = ?",
        params=(person_id,),
        as_of_date="2025-12-01T00:00:00Z",
    )
"""
from __future__ import annotations

import sqlite3
from typing import Any


def add_bitemporal_columns(conn: sqlite3.Connection, table: str) -> bool:
    """Add valid_from and valid_until columns. Returns True if added new.

    Idempotent: safe to call on every channel construction. Catches the
    'duplicate column' error so re-running is a no-op.
    """
    added = False
    for col in ("valid_from", "valid_until"):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            added = True
        except sqlite3.OperationalError as e:
            # "duplicate column name" — already migrated. Anything else
            # we re-raise so the operator sees real schema problems.
            if "duplicate column" not in str(e).lower():
                raise
    if added:
        # Add indexes (these are independent CREATE IF NOT EXISTS so safe).
        if table == "people_facts":
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_people_facts_valid_from "
                "ON people_facts(valid_from) WHERE valid_from IS NOT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_people_facts_valid_window "
                "ON people_facts(person_id, kind, valid_from, valid_until)"
            )
        elif table == "recalls":
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recalls_valid_from "
                "ON recalls(valid_from) WHERE valid_from IS NOT NULL"
            )
        conn.commit()
    return added


def as_of_clause(date_iso: str, column_pair: tuple[str, str] = ("valid_from", "valid_until")) -> str:
    """Return a SQL fragment that filters rows valid on a given date.

    A row is 'valid as of date' when:
        valid_from <= date AND (valid_until IS NULL OR valid_until > date)

    Returns a fragment like:
        ( (valid_from IS NULL OR valid_from <= '2025-12-01T00:00:00Z')
          AND (valid_until IS NULL OR valid_until > '2025-12-01T00:00:00Z') )

    Note: valid_from IS NULL is treated as "valid forever in the past"
    (existing rows from before bitemporal augmentation). This is the
    honest default — we don't know when they became true, so we don't
    assume they weren't.
    """
    vf, vu = column_pair
    # Bind the date string by simple repr to keep the fragment SQL-safe
    # when callers pass it as a literal. The expected usage is parameterized
    # at the caller's INSERT/SELECT site; this is a fragment helper, not
    # a query executor.
    safe = date_iso.replace("'", "")
    return (
        f"( ({vf} IS NULL OR {vf} <= '{safe}') "
        f"AND ({vu} IS NULL OR {vu} > '{safe}') )"
    )


def as_of_filter(
    conn: sqlite3.Connection,
    *,
    sql: str,
    params: tuple = (),
    as_of_date: str,
    column_pair: tuple[str, str] = ("valid_from", "valid_until"),
) -> list[tuple]:
    """Run a SELECT and return only rows valid as of a given date.

    The caller's SQL is run unchanged; we filter the results in Python by
    inspecting the row's valid_from/valid_until columns. This keeps the
    helper SQL-injection-safe at the cost of doing the filter post-fetch.

    For high-volume cases, use ``as_of_clause`` to inline the filter.

    Returns rows where the row's valid window contains as_of_date.
    """
    rows = conn.execute(sql, params).fetchall()
    # Discover column positions via cursor description on a single-row fetch
    cur = conn.execute(sql + " LIMIT 1", params)
    desc = cur.description or []
    cur.fetchall()
    cols = [d[0] for d in desc]
    try:
        vf_idx = cols.index(column_pair[0])
    except ValueError:
        return rows  # no valid_from column — nothing to filter on
    try:
        vu_idx = cols.index(column_pair[1])
    except ValueError:
        vu_idx = None
    out: list[tuple] = []
    for row in rows:
        vf = row[vf_idx] if vf_idx < len(row) else None
        vu = row[vu_idx] if vu_idx is not None and vu_idx < len(row) else None
        if vf is not None and vf > as_of_date:
            continue
        if vu is not None and vu <= as_of_date:
            continue
        out.append(row)
    return out


__all__ = ["add_bitemporal_columns", "as_of_clause", "as_of_filter"]
