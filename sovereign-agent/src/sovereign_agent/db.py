"""atoms.db connection + schema bootstrap. Architecture §8."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from .config import SETTINGS


def open_atoms_db() -> sqlite3.Connection:
    """Open atoms.db with sqlite-vec loaded and the v0.1 schema applied."""
    conn = sqlite3.connect(SETTINGS.paths.atoms_db, isolation_level=None)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")

    schema = (Path(__file__).parent.parent.parent / "sql" / "002_atoms.sql").read_text()
    # Strip the PRAGMAs from the schema file (we already applied them); executescript
    # handles the rest.
    conn.executescript(schema)
    return conn
