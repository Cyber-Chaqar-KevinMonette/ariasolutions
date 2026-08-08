"""Event log — architecture §8a.

Contract:
  events.jsonl is the durable source of truth.
  The SQLite events table is a derived projection, rebuilt by tail_to_sqlite().

Write path:
  emit_event(...) -> ULID -> JSON -> O_APPEND to today's events.jsonl -> batched fsync().

Read paths:
  Hot path:  query SQLite events table (after tail-consumer has caught up).
  Audit:     read events.jsonl directly. JSONL wins on disagreement.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ulid import ULID

from .config import SETTINGS

_LOCK = threading.Lock()
_PENDING_FSYNC = 0
_LAST_FSYNC_AT = 0.0


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def emit_event(
    flag: str,
    *,
    plane: str,
    trace_id: str,
    parent_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Append one event to events.jsonl. Returns the event ULID.

    Atomicity guarantee:
      O_APPEND is atomic for writes < PIPE_BUF (4096 bytes on Linux).
      Payloads larger than SETTINGS.event_max_inline_bytes are written to the blob
      store and the event references the blob hash instead of inlining.
    """
    global _PENDING_FSYNC, _LAST_FSYNC_AT
    payload = payload or {}
    event_id = str(ULID())
    record = {
        "event_id": event_id,
        "ts": _utc_now_rfc3339(),
        "flag": flag,
        "plane": plane,
        "trace_id": trace_id,
        "parent_id": parent_id,
        "payload": payload,
    }
    line = _canonical_json(record)
    if len(line.encode("utf-8")) > SETTINGS.event_max_inline_bytes:
        # Spill payload to blob store; replace with reference.
        blob_hash = _spill_to_blobs(payload)
        record["payload"] = {"_blob_ref": blob_hash}
        line = _canonical_json(record)

    line += "\n"
    encoded = line.encode("utf-8")
    path = SETTINGS.paths.events_jsonl

    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as f:
            f.write(encoded)
            _PENDING_FSYNC += 1
            now = time.monotonic()
            if (
                _PENDING_FSYNC >= SETTINGS.event_fsync_every_n
                or (now - _LAST_FSYNC_AT) >= SETTINGS.event_fsync_every_seconds
            ):
                f.flush()
                os.fsync(f.fileno())
                _PENDING_FSYNC = 0
                _LAST_FSYNC_AT = now

    return event_id


def force_fsync() -> None:
    """Force-flush pending events. Call before clean shutdown."""
    global _PENDING_FSYNC, _LAST_FSYNC_AT
    with _LOCK:
        path = SETTINGS.paths.events_jsonl
        if path.exists():
            with path.open("ab") as f:
                f.flush()
                os.fsync(f.fileno())
        _PENDING_FSYNC = 0
        _LAST_FSYNC_AT = time.monotonic()


def _spill_to_blobs(payload: dict[str, Any]) -> str:
    """Content-addressed blob storage for oversized event payloads."""
    import hashlib

    data = _canonical_json(payload).encode("utf-8")
    h = hashlib.sha256(data).hexdigest()
    blob_path = SETTINGS.paths.blobs_dir / h[:2] / h[2:]
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    if not blob_path.exists():
        # Atomic write
        tmp = blob_path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(blob_path)
    return h


# ─── Tail consumer: JSONL → SQLite events projection ────────────────────────


def init_events_db() -> sqlite3.Connection:
    """Open events.db with the schema from sql/001_events.sql applied."""
    conn = sqlite3.connect(SETTINGS.paths.events_db, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    schema = (Path(__file__).parent.parent.parent / "sql" / "001_events.sql").read_text()
    conn.executescript(schema)
    return conn


def tail_to_sqlite(conn: sqlite3.Connection, *, jsonl_path: Path | None = None) -> int:
    """Idempotently ingest events.jsonl into SQLite. Returns count inserted.

    Resume semantics: ingest_cursor.last_byte_offset tells us where we left off.
    INSERT OR IGNORE on event_id PRIMARY KEY makes re-ingest of overlap a no-op.
    """
    jsonl_path = jsonl_path or SETTINGS.paths.events_jsonl
    if not jsonl_path.exists():
        return 0

    cursor = conn.execute(
        "SELECT last_byte_offset FROM ingest_cursor WHERE id = 1"
    ).fetchone()
    offset = cursor[0] if cursor else 0

    inserted = 0
    skipped_corrupt = 0
    with jsonl_path.open("rb") as f:
        f.seek(offset)
        # readline()-based loop with manual offset accounting. `for raw in f`
        # uses read-ahead buffering, making f.tell() unreliable mid-iteration —
        # and the old `break` on any JSONDecodeError meant a corrupt line
        # MID-file (torn write, disk error) halted all further ingestion
        # forever, since the cursor never advanced past it.
        new_offset = offset
        while True:
            raw = f.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                # Genuine partial line at the tail (writer mid-append) — stop
                # WITHOUT advancing past it; next pass retries once complete.
                break
            try:
                rec = json.loads(raw)
            except ValueError:
                # Complete-but-corrupt line — skip it and ADVANCE, so one bad
                # line can never silently wedge ingestion. Counted and
                # surfaced below rather than swallowed. ValueError covers both
                # JSONDecodeError AND UnicodeDecodeError — real disk corruption
                # produces invalid UTF-8 bytes, which json.loads raises as the
                # latter (previously an unhandled crash, not even a wedge).
                skipped_corrupt += 1
                new_offset += len(raw)
                continue
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO events "
                    "(event_id, ts, flag, plane, trace_id, parent_id, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        rec["event_id"],
                        rec["ts"],
                        rec["flag"],
                        rec["plane"],
                        rec["trace_id"],
                        rec.get("parent_id"),
                        _canonical_json(rec.get("payload", {})),
                    ),
                )
                # rowcount is the actual number of rows affected by THIS statement
                # (1 if inserted, 0 if the IGNORE clause matched a duplicate).
                inserted += cur.rowcount if cur.rowcount > 0 else 0
            except (KeyError, sqlite3.Error):
                pass
            new_offset += len(raw)

    now = _utc_now_rfc3339()
    conn.execute(
        "INSERT INTO ingest_cursor (id, last_byte_offset, updated_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_byte_offset = excluded.last_byte_offset, "
        "updated_at = excluded.updated_at",
        (new_offset, now),
    )
    if skipped_corrupt:
        # Surface corruption instead of swallowing it — this lands in the
        # jsonl and is ingested (and visible in the cockpit) on the next pass.
        emit_event(
            "ingest-skip-x",
            plane="control",
            trace_id="ingest",
            payload={"skipped_corrupt_lines": skipped_corrupt, "jsonl": str(jsonl_path)},
        )
    return inserted


@contextlib.contextmanager
def trace(trace_id: str | None = None):
    """Context manager that yields a trace_id; emits start-d / end-d bookends."""
    tid = trace_id or str(ULID())
    start_id = emit_event("trace-start-d", plane="control", trace_id=tid)
    try:
        yield tid
    finally:
        emit_event("trace-end-d", plane="control", trace_id=tid, parent_id=start_id)


# ─── Sub-events (Kevin, 2026-07-21) ────────────────────────────────────────
#
# "harden her events system... maybe she needs events that have sub
# events." The mechanism already existed -- emit_event's own `parent_id`
# parameter, stored end-to-end (JSONL AND the SQLite projection above) --
# but almost nothing used it (trace()'s own start/end bookend was the
# only caller anywhere in this codebase) and there was no way to read a
# parent/children relationship back out. emit_child_event() below is a
# discoverable, named entry point for the WRITE side; event_children() /
# event_tree() are the READ side -- "understand how to use them all more
# intelligently" means being able to see the tree, not just write it.


def emit_child_event(
    flag: str,
    *,
    plane: str,
    trace_id: str,
    parent_id: str,
    payload: dict[str, Any] | None = None,
) -> str:
    """Emit an event as an explicit CHILD of `parent_id` (an event_id
    returned by an earlier emit_event/emit_child_event call). Purely a
    named, discoverable wrapper over emit_event's existing parent_id
    parameter -- same durability guarantees, same JSONL+SQLite path.
    Use this whenever several events describe sub-steps of one larger
    operation (e.g. every event about ONE subtask's lifecycle, or a
    long tool call's progress pings) so the relationship is queryable
    later via event_children()/event_tree(), not just implied by reading
    timestamps in order.
    """
    return emit_event(flag, plane=plane, trace_id=trace_id,
                      parent_id=parent_id, payload=payload)


def event_children(parent_id: str, *, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Every event directly recorded as a child of `parent_id`, oldest
    first. Reads the SQLite projection (already carries parent_id per
    tail_to_sqlite's INSERT above) -- call `tail_to_sqlite()` first if
    the events you're looking for were only just emitted and the
    background tailer hasn't caught up yet. Returns [] (never raises) if
    the DB is missing or the id has no children."""
    own_conn = conn is None
    if conn is None:
        if not SETTINGS.paths.events_db.exists():
            return []
        conn = sqlite3.connect(SETTINGS.paths.events_db)
    try:
        rows = conn.execute(
            "SELECT event_id, ts, flag, plane, trace_id, parent_id, payload "
            "FROM events WHERE parent_id = ? ORDER BY ts ASC",
            (parent_id,),
        ).fetchall()
        return [
            {"event_id": r[0], "ts": r[1], "flag": r[2], "plane": r[3],
             "trace_id": r[4], "parent_id": r[5],
             "payload": json.loads(r[6]) if r[6] else {}}
            for r in rows
        ]
    except sqlite3.Error:
        return []
    finally:
        if own_conn:
            conn.close()


def event_tree(root_event_id: str, *, max_depth: int = 5) -> dict:
    """The full nested parent -> children structure rooted at
    `root_event_id`, up to `max_depth` levels (a bounded recursion floor
    against a corrupt/cyclic parent_id chain -- should never happen, but
    this is an observability reader, not a place to hang on bad data).
    Returns ``{"event_id": ..., "children": [...]}`` recursively; a leaf
    has an empty "children" list."""
    if not SETTINGS.paths.events_db.exists():
        return {"event_id": root_event_id, "children": []}
    conn = sqlite3.connect(SETTINGS.paths.events_db)
    try:
        def _build(event_id: str, depth: int) -> dict:
            node = {"event_id": event_id, "children": []}
            if depth >= max_depth:
                return node
            for child in event_children(event_id, conn=conn):
                node["children"].append(_build(child["event_id"], depth + 1))
            return node
        return _build(root_event_id, 0)
    finally:
        conn.close()
