"""Daily seal job. Architecture §8a + MOS §20.3.

Once per day (intended via systemd timer at 00:05 UTC), compute a Merkle
root over the previous day's events.jsonl and write it to atoms.db.seals.
This gives a tamper-evident audit trail: any change to past events shows
up as a different root.

Late-arriving events (e.g., a clock-skew correction) write a ``late_patch``
seal that references the day they patched. The original seal stays.

This module is also runnable as a script: ``python -m sovereign_agent.seal``.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import SETTINGS
from .db import open_atoms_db
from .events import emit_event


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _merkle_root(leaves: list[str]) -> str:
    """Standard binary Merkle tree, duplicating the last leaf if odd count."""
    if not leaves:
        return _sha256_hex(b"")
    nodes = [bytes.fromhex(h) for h in leaves]
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])  # duplicate last to pair
        nodes = [
            hashlib.sha256(nodes[i] + nodes[i + 1]).digest()
            for i in range(0, len(nodes), 2)
        ]
    return nodes[0].hex()


def _events_jsonl_for_date(target_date: date) -> Path:
    return SETTINGS.paths.events_dir / f"events-{target_date.isoformat()}.jsonl"


def compute_seal(target_date: date) -> dict | None:
    """Compute the seal for one day. Returns a dict ready for insert, or None
    if the JSONL is missing/empty.
    """
    path = _events_jsonl_for_date(target_date)
    if not path.exists():
        return None

    leaves: list[str] = []
    first_event: str | None = None
    last_event: str | None = None

    with path.open("rb") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                eid = rec.get("event_id")
                if not eid:
                    continue
            except json.JSONDecodeError:
                continue
            leaves.append(_sha256_hex(line))
            if first_event is None:
                first_event = eid
            last_event = eid

    if not leaves:
        return None

    root = _merkle_root(leaves)
    return {
        "seal_date": target_date.isoformat(),
        "merkle_root": root,
        "event_count": len(leaves),
        "first_event": first_event,
        "last_event": last_event,
        "sealed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def write_seal(conn: sqlite3.Connection, seal: dict, *, late_patch_of: str | None = None) -> None:
    """Insert a seal row. If a seal for that date already exists and
    ``late_patch_of`` is None, this raises (use ``late_patch_of=date_str``
    to patch instead).
    """
    conn.execute(
        "INSERT INTO seals "
        "(seal_date, merkle_root, event_count, first_event, last_event, "
        "sealed_at, late_patch_of) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            seal["seal_date"],
            seal["merkle_root"],
            seal["event_count"],
            seal["first_event"],
            seal["last_event"],
            seal["sealed_at"],
            late_patch_of,
        ),
    )


def seal_yesterday() -> str | None:
    """Compute and persist yesterday's seal. Returns the merkle root (hex)
    or None if there were no events.
    """
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1))
    seal = compute_seal(yesterday)
    if seal is None:
        emit_event(
            "seal-x",
            plane="control",
            trace_id="seal-job",
            payload={"reason": "no_events", "date": yesterday.isoformat()},
        )
        return None

    conn = open_atoms_db()
    try:
        # If a seal already exists for that date, this is a late-patch
        existing = conn.execute(
            "SELECT seal_date FROM seals WHERE seal_date = ? AND late_patch_of IS NULL",
            (yesterday.isoformat(),),
        ).fetchone()
        late_patch_of = yesterday.isoformat() if existing else None
        if late_patch_of:
            seal["seal_date"] = f"{yesterday.isoformat()}.patch-{seal['sealed_at']}"
        write_seal(conn, seal, late_patch_of=late_patch_of)
        conn.commit()
    finally:
        conn.close()

    emit_event(
        "seal-d",
        plane="control",
        trace_id="seal-job",
        payload={
            "date": yesterday.isoformat(),
            "merkle_root": seal["merkle_root"],
            "event_count": seal["event_count"],
            "late_patch": bool(late_patch_of),
        },
    )
    return seal["merkle_root"]


def verify_seal(target_date: date) -> tuple[bool, str]:
    """Recompute the seal for a date and compare to the stored value.

    Returns ``(matches, message)``. ``matches=False`` means the events
    file has changed since it was sealed — investigate.
    """
    fresh = compute_seal(target_date)
    if fresh is None:
        return False, f"no events.jsonl for {target_date}"

    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT merkle_root FROM seals WHERE seal_date = ? AND late_patch_of IS NULL",
            (target_date.isoformat(),),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return False, f"no seal recorded for {target_date}"

    stored = row[0]
    matches = stored == fresh["merkle_root"]
    msg = (
        f"seal MATCHES for {target_date}"
        if matches
        else f"seal MISMATCH for {target_date}: stored={stored[:16]}... fresh={fresh['merkle_root'][:16]}..."
    )
    return matches, msg


if __name__ == "__main__":
    root = seal_yesterday()
    if root:
        print(f"sealed yesterday: {root}")
    else:
        print("no events to seal")
