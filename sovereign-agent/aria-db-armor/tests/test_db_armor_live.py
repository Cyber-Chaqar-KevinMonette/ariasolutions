"""Behavior tests for aria-db-armor, promoted to live tests/ — assert every
previously-unhardened SQLite store now carries the proven pragma block
(busy_timeout=5000 per connection; WAL where it was missing). Plain
imports, no shadow copy, no sys.modules manipulation.
"""
from __future__ import annotations

import sqlite3


def _pragmas(conn: sqlite3.Connection) -> dict:
    return {
        "busy_timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
        "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
    }


def test_palace_connection_is_armored(tmp_path):
    from sovereign_agent.palace import Palace

    p = Palace(tmp_path / "palace.db")
    with p._connect() as conn:
        got = _pragmas(conn)
    assert got["busy_timeout"] == 5000
    assert got["journal_mode"] == "wal"
    p.close()


def test_persistence_store_connection_is_armored(tmp_path):
    from sovereign_agent.persistence.store import ErebloStore

    store = ErebloStore(tmp_path / "persist.db")
    with store._conn() as conn:
        got = _pragmas(conn)
    assert got["busy_timeout"] == 5000
    assert got["journal_mode"] == "wal"


def test_aegis_connection_is_armored(tmp_path):
    from sovereign_agent.aegis.bitemporal import BitemporalStore

    store = BitemporalStore(tmp_path / "aegis" / "ledger.db")
    with store._conn() as conn:
        got = _pragmas(conn)
    assert got["busy_timeout"] == 5000
    assert got["journal_mode"] == "wal"


def test_feedback_connect_helper_is_armored(tmp_path):
    from sovereign_agent.feedback.feedback import _connect

    conn = _connect(tmp_path / "feedback.db")
    got = _pragmas(conn)
    conn.close()
    assert got["busy_timeout"] == 5000
    assert got["journal_mode"] == "wal"


def test_persistence_survives_concurrent_writer_holding_the_db(tmp_path):
    """The real-world collision this module exists for: a second connection
    writes while another holds a transaction. With busy_timeout=5000 + WAL,
    the reader/writer waits instead of instantly throwing
    'database is locked'."""
    from sovereign_agent.persistence.store import ErebloStore

    db_path = tmp_path / "persist.db"
    store = ErebloStore(db_path)

    # An external writer (whole lifecycle inside its own thread — sqlite3
    # connections are single-thread by default) holds a write transaction
    # briefly, then commits while the store attempts its own write.
    import threading
    import time

    holding = threading.Event()

    def _hold_and_release():
        blocker = sqlite3.connect(db_path)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            blocker.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('blocker', '1')"
            )
            holding.set()
            time.sleep(0.3)
            blocker.commit()
        finally:
            blocker.close()

    t = threading.Thread(target=_hold_and_release)
    t.start()
    try:
        assert holding.wait(timeout=5.0), "blocker thread never acquired the lock"
        # Without busy_timeout this raises sqlite3.OperationalError immediately.
        with store._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('armor', 'ok')"
            )
    finally:
        t.join()

    with store._conn() as conn:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='armor'").fetchone()
    assert row is not None and row[0] == "ok"
