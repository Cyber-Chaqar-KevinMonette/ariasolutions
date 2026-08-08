"""Events durability tests. Architecture §8a.

Verifies:
  - emit_event appends to events.jsonl
  - tail_to_sqlite ingests JSONL into the SQLite projection
  - Re-running tail is idempotent (no duplicate rows)
  - JSONL is the source of truth: drop SQLite events table, rebuild from JSONL
"""
from __future__ import annotations

import json

from sovereign_agent.config import SETTINGS
from sovereign_agent.events import (
    emit_event,
    force_fsync,
    init_events_db,
    tail_to_sqlite,
)


def test_emit_appends_to_jsonl():
    eid = emit_event(
        "test-d", plane="control", trace_id="t1", payload={"k": "v"}
    )
    force_fsync()
    path = SETTINGS.paths.events_jsonl
    assert path.exists()
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event_id"] == eid
    assert rec["flag"] == "test-d"
    assert rec["payload"] == {"k": "v"}


def test_tail_ingests_into_sqlite():
    e1 = emit_event("a-d", plane="control", trace_id="t1")
    e2 = emit_event("b-d", plane="tool", trace_id="t1")
    force_fsync()

    conn = init_events_db()
    inserted = tail_to_sqlite(conn)
    assert inserted >= 2

    rows = conn.execute(
        "SELECT event_id, flag FROM events ORDER BY event_id"
    ).fetchall()
    ids = [r[0] for r in rows]
    flags = [r[1] for r in rows]
    assert e1 in ids
    assert e2 in ids
    assert "a-d" in flags
    assert "b-d" in flags


def test_tail_is_idempotent():
    emit_event("once-d", plane="control", trace_id="t-idem")
    force_fsync()
    conn = init_events_db()

    n1 = tail_to_sqlite(conn)
    # Re-running tail without new events should insert zero new rows
    # (cursor advanced last time)
    n2 = tail_to_sqlite(conn)
    assert n2 == 0
    # And no duplicate rows
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE flag='once-d'"
    ).fetchone()[0]
    assert count == 1


def test_rebuild_from_jsonl_after_dropping_table():
    emit_event("survive-d", plane="control", trace_id="t-rebuild")
    force_fsync()
    conn = init_events_db()
    tail_to_sqlite(conn)
    # Wipe the SQLite projection
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM ingest_cursor")
    # Rebuild from JSONL
    inserted = tail_to_sqlite(conn)
    assert inserted >= 1
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE flag='survive-d'"
    ).fetchone()[0]
    assert count == 1


def test_large_payload_spills_to_blob_store():
    """Payloads exceeding event_max_inline_bytes must be spilled to the blob store.

    The inline event should contain a _blob_ref instead of the raw payload.
    """
    from sovereign_agent.config import SETTINGS as S
    # Build a payload just over the inline limit
    big_value = "x" * (S.event_max_inline_bytes + 500)
    eid = emit_event(
        "blob-spill-d",
        plane="control",
        trace_id="t-spill",
        payload={"data": big_value},
    )
    force_fsync()

    path = S.paths.events_jsonl
    lines = path.read_text().splitlines()
    matching = [json.loads(l) for l in lines if json.loads(l).get("event_id") == eid]
    assert len(matching) == 1
    rec = matching[0]
    # Payload should have been replaced with a blob ref
    assert "_blob_ref" in rec["payload"]
    blob_hash = rec["payload"]["_blob_ref"]
    # The blob file must actually exist
    blob_path = S.paths.blobs_dir / blob_hash[:2] / blob_hash[2:]
    assert blob_path.exists()


def test_blob_spill_idempotent():
    """Writing the same oversized payload twice should not duplicate the blob."""
    from sovereign_agent.config import SETTINGS as S
    big_value = "y" * (S.event_max_inline_bytes + 500)
    e1 = emit_event("blob-idem-d", plane="control", trace_id="t-idem2", payload={"d": big_value})
    e2 = emit_event("blob-idem-d", plane="control", trace_id="t-idem2", payload={"d": big_value})
    force_fsync()
    # Both events should have the same blob hash (content-addressed)
    path = S.paths.events_jsonl
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    refs = [l["payload"]["_blob_ref"] for l in lines if l.get("event_id") in (e1, e2)]
    assert len(refs) == 2
    assert refs[0] == refs[1]  # same hash — content-addressed, no duplication


def test_partial_trailing_line_does_not_corrupt_ingest():
    """If the JSONL has a partial trailing line (e.g., write interrupted),
    tail_to_sqlite must stop cleanly and not advance past it."""
    emit_event("clean-d", plane="control", trace_id="t-partial")
    force_fsync()
    # Append a deliberately broken trailing line
    path = SETTINGS.paths.events_jsonl
    with path.open("ab") as f:
        f.write(b'{"event_id": "broken", "flag": "incomplete-')  # no newline, no closing brace

    conn = init_events_db()
    # Should ingest the good line but stop at the broken one
    n = tail_to_sqlite(conn)
    assert n >= 1
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE flag='clean-d'"
    ).fetchone()[0]
    assert count == 1
    # The broken record must NOT have been inserted
    bad = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_id='broken'"
    ).fetchone()[0]
    assert bad == 0


def test_corrupt_middle_line_does_not_wedge_ingestion():
    """The bug this guards: a corrupt-but-COMPLETE line mid-file used to
    `break` the ingest loop without advancing the cursor — permanently
    halting all downstream event ingestion. Corrupt complete lines must be
    skipped (and counted), with later good events still ingested."""
    emit_event("before-corrupt-d", plane="control", trace_id="t-wedge")
    force_fsync()
    path = SETTINGS.paths.events_jsonl
    with path.open("ab") as f:
        f.write(b'{"event_id": "torn", "flag": "corrupt-\xff\xfe garbage"}\n')  # complete but invalid
    emit_event("after-corrupt-d", plane="control", trace_id="t-wedge")
    force_fsync()

    conn = init_events_db()
    tail_to_sqlite(conn)
    flags = {r[0] for r in conn.execute("SELECT flag FROM events").fetchall()}
    assert "before-corrupt-d" in flags
    assert "after-corrupt-d" in flags, "ingestion wedged on the corrupt middle line"
    # A second pass must not re-process or duplicate anything.
    n2 = tail_to_sqlite(conn)
    # Only the ingest-skip-x visibility event (emitted by the first pass) may arrive now.
    flags2 = [r[0] for r in conn.execute("SELECT flag FROM events WHERE flag='after-corrupt-d'").fetchall()]
    assert len(flags2) == 1


def test_partial_tail_resumes_correctly_after_line_completes():
    """A partial trailing line must not advance the cursor; once the line is
    completed by the writer, the next pass must ingest it exactly once."""
    path = SETTINGS.paths.events_jsonl
    emit_event("first-d", plane="control", trace_id="t-resume")
    force_fsync()
    # Simulate a mid-append crash: half a record, no newline.
    partial = b'{"event_id": "resume-me", "ts": "2026-07-04T00:00:00.000000Z", "flag": "resumed-d", "plane": "control", "trace_id": "t-resume"'
    with path.open("ab") as f:
        f.write(partial)

    conn = init_events_db()
    tail_to_sqlite(conn)
    assert conn.execute("SELECT COUNT(*) FROM events WHERE flag='resumed-d'").fetchone()[0] == 0

    # The writer finishes the line.
    with path.open("ab") as f:
        f.write(b', "payload": {}}\n')
    tail_to_sqlite(conn)
    assert conn.execute("SELECT COUNT(*) FROM events WHERE flag='resumed-d'").fetchone()[0] == 1
    # Idempotency: a third pass inserts nothing new.
    assert tail_to_sqlite(conn) == 0


def test_skipped_corrupt_lines_are_surfaced_not_silent():
    """Corruption must be visible: a pass that skips corrupt lines emits an
    ingest-skip-x event recording how many."""
    path = SETTINGS.paths.events_jsonl
    emit_event("good-d", plane="control", trace_id="t-visible")
    force_fsync()
    with path.open("ab") as f:
        f.write(b'not json at all\n')

    conn = init_events_db()
    tail_to_sqlite(conn)
    # The visibility event was appended to the jsonl; a second pass ingests it.
    tail_to_sqlite(conn)
    row = conn.execute(
        "SELECT payload FROM events WHERE flag='ingest-skip-x'"
    ).fetchone()
    assert row is not None, "skipped corruption was not surfaced"
    payload = json.loads(row[0])
    assert payload["skipped_corrupt_lines"] == 1


# ─── Sub-events (Kevin, 2026-07-21) ────────────────────────────────────────


def test_emit_child_event_is_a_thin_wrapper_over_parent_id():
    from sovereign_agent.events import emit_child_event

    parent_id = "test-parent-1"
    child_id = emit_child_event(
        "child-d", plane="control", trace_id="t1", parent_id=parent_id,
        payload={"k": "v"},
    )
    force_fsync()
    path = SETTINGS.paths.events_jsonl
    rec = json.loads(path.read_text().splitlines()[-1])
    assert rec["event_id"] == child_id
    assert rec["parent_id"] == parent_id
    assert rec["payload"] == {"k": "v"}


def test_event_children_reads_the_sqlite_projection():
    from sovereign_agent.events import emit_child_event, event_children

    parent_id = emit_event("parent-d", plane="control", trace_id="t1")
    c1 = emit_child_event("child-a-d", plane="control", trace_id="t1", parent_id=parent_id)
    c2 = emit_child_event("child-b-d", plane="control", trace_id="t1", parent_id=parent_id)
    # a distractor with a DIFFERENT parent — must not show up
    emit_child_event("unrelated-d", plane="control", trace_id="t1", parent_id="someone-else")
    force_fsync()

    conn = init_events_db()
    tail_to_sqlite(conn)

    children = event_children(parent_id, conn=conn)
    ids = {c["event_id"] for c in children}
    assert ids == {c1, c2}
    flags = {c["flag"] for c in children}
    assert flags == {"child-a-d", "child-b-d"}


def test_event_children_is_never_raises_with_no_db():
    from sovereign_agent.events import event_children

    assert event_children("nonexistent-parent") == []


def test_event_tree_nests_grandchildren():
    from sovereign_agent.events import emit_child_event, event_tree

    root = emit_event("root-d", plane="control", trace_id="t1")
    mid = emit_child_event("mid-d", plane="control", trace_id="t1", parent_id=root)
    emit_child_event("leaf-d", plane="control", trace_id="t1", parent_id=mid)
    force_fsync()

    conn = init_events_db()
    tail_to_sqlite(conn)
    conn.close()  # event_tree opens its own connection internally

    tree = event_tree(root)
    assert tree["event_id"] == root
    assert len(tree["children"]) == 1
    assert tree["children"][0]["event_id"] == mid
    assert len(tree["children"][0]["children"]) == 1
    assert tree["children"][0]["children"][0]["event_id"] != root  # the leaf


def test_event_tree_depth_is_bounded():
    """A max_depth floor against a corrupt/cyclic chain -- this is an
    observability reader, it must never hang on bad data."""
    from sovereign_agent.events import emit_child_event, event_tree

    root = emit_event("root-d", plane="control", trace_id="t1")
    current = root
    for i in range(10):
        current = emit_child_event(f"depth-{i}-d", plane="control",
                                   trace_id="t1", parent_id=current)
    force_fsync()
    conn = init_events_db()
    tail_to_sqlite(conn)
    conn.close()

    tree = event_tree(root, max_depth=3)

    def _depth(node, d=0):
        if not node["children"]:
            return d
        return _depth(node["children"][0], d + 1)

    assert _depth(tree) <= 3
