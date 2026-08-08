"""patcher.py — Workstream Gym #4: aria-db-armor.

Uniform SQLite hardening. atoms.db and events.db already carry the proven
pragma block (db.py:19-22: WAL + synchronous=NORMAL + busy_timeout=5000);
every other store was missing some or all of it — so a concurrent cockpit +
`sov` CLI + agent subprocess could intermittently throw "database is
locked". busy_timeout is PER-CONNECTION (unlike WAL, which persists in the
DB file), which is why every patch here lands at a connect site, not in
schema SQL.

Five targets, all anchored + idempotent (MARK below):
  1. palace.py    — busy_timeout + synchronous at the singleton connect
                    (WAL already set by its schema SQL).
  2. shards.py    — busy_timeout at the per-channel connect (WAL/sync
                    already there) + at the ad-hoc inspect connect.
  3. persistence/store.py — busy_timeout + synchronous in _conn() (WAL
                    already set by SCHEMA_SQL; this store had NEITHER
                    per-connection pragma — the weakest of the five, and
                    it holds sessions/projects/clock/workflow).
  4. feedback/feedback.py — one new _connect() helper carrying the full
                    block; the 4 identical bare connect sites route
                    through it.
  5. aegis/bitemporal.py — WAL + busy_timeout + synchronous in _conn();
                    busy_timeout at the one-shot _init_db connect.
"""
from __future__ import annotations

MARK = "db-armor-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


def _replace_n(text: str, old: str, new: str, *, expected: int, label: str) -> str:
    found = text.count(old)
    if found != expected:
        raise PatchError(f"{label}: expected exactly {expected} occurrences, found {found}")
    return text.replace(old, new)


# ═══════════════════════════════════════════════════════════════════════
# palace.py
# ═══════════════════════════════════════════════════════════════════════

PALACE_ANCHOR = (
    "                self._conn = sqlite3.connect(self.db_path, isolation_level=None)\n"
    "                self._conn.row_factory = sqlite3.Row\n"
)
PALACE_NEW = (
    "                self._conn = sqlite3.connect(self.db_path, isolation_level=None)\n"
    f'                self._conn.execute("PRAGMA busy_timeout = 5000")  # {MARK}\n'
    '                self._conn.execute("PRAGMA synchronous = NORMAL")\n'
    "                self._conn.row_factory = sqlite3.Row\n"
)


def patch_palace(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, PALACE_ANCHOR, PALACE_NEW, label="palace.py connect anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# shards.py
# ═══════════════════════════════════════════════════════════════════════

SHARDS_CONNECT_ANCHOR = (
    "    conn = sqlite3.connect(str(path), isolation_level=None)\n"
    '    conn.execute("PRAGMA journal_mode = WAL")\n'
)
SHARDS_CONNECT_NEW = (
    "    conn = sqlite3.connect(str(path), isolation_level=None)\n"
    f'    conn.execute("PRAGMA busy_timeout = 5000")  # {MARK}\n'
    '    conn.execute("PRAGMA journal_mode = WAL")\n'
)

SHARDS_INSPECT_ANCHOR = (
    "                c = sqlite3.connect(str(abs_path))\n"
)
SHARDS_INSPECT_NEW = (
    "                c = sqlite3.connect(str(abs_path))\n"
    f'                c.execute("PRAGMA busy_timeout = 5000")  # {MARK}\n'
)


def patch_shards(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SHARDS_CONNECT_ANCHOR, SHARDS_CONNECT_NEW, label="shards.py connect anchor")
    text = _replace_once(text, SHARDS_INSPECT_ANCHOR, SHARDS_INSPECT_NEW, label="shards.py inspect anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# persistence/store.py
# ═══════════════════════════════════════════════════════════════════════

PERSISTENCE_ANCHOR = (
    "        conn = sqlite3.connect(\n"
    '            self._path, isolation_level="IMMEDIATE",\n'
    "            detect_types=sqlite3.PARSE_DECLTYPES,\n"
    "        )\n"
    "        conn.row_factory = sqlite3.Row\n"
)
PERSISTENCE_NEW = (
    "        conn = sqlite3.connect(\n"
    '            self._path, isolation_level="IMMEDIATE",\n'
    "            detect_types=sqlite3.PARSE_DECLTYPES,\n"
    "        )\n"
    f'        conn.execute("PRAGMA busy_timeout = 5000")  # {MARK}\n'
    '        conn.execute("PRAGMA synchronous = NORMAL")\n'
    "        conn.row_factory = sqlite3.Row\n"
)


def patch_persistence(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, PERSISTENCE_ANCHOR, PERSISTENCE_NEW, label="persistence/store.py connect anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# feedback/feedback.py
# ═══════════════════════════════════════════════════════════════════════

FEEDBACK_HELPER_ANCHOR = (
    "from __future__ import annotations\n"
    "\n"
    "import json\n"
    "import sqlite3\n"
)
FEEDBACK_HELPER_NEW = (
    "from __future__ import annotations\n"
    "\n"
    "import json\n"
    "import sqlite3\n"
    "\n"
    "\n"
    f"def _connect(path) -> sqlite3.Connection:  # {MARK}\n"
    '    """One hardened connect for every feedback DB access — the same\n'
    "    pragma block atoms.db/events.db carry (db.py), so a concurrent\n"
    '    cockpit + CLI can\'t throw \'database is locked\' here."""\n'
    "    conn = sqlite3.connect(str(path))\n"
    '    conn.execute("PRAGMA busy_timeout = 5000")\n'
    '    conn.execute("PRAGMA journal_mode = WAL")\n'
    '    conn.execute("PRAGMA synchronous = NORMAL")\n'
    "    return conn\n"
)

FEEDBACK_SITE_OLD = "conn = sqlite3.connect(str(self._store._path))"
FEEDBACK_SITE_NEW = "conn = _connect(self._store._path)"


def patch_feedback(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, FEEDBACK_HELPER_ANCHOR, FEEDBACK_HELPER_NEW, label="feedback.py helper anchor")
    text = _replace_n(text, FEEDBACK_SITE_OLD, FEEDBACK_SITE_NEW, expected=4, label="feedback.py connect sites")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# aegis/bitemporal.py
# ═══════════════════════════════════════════════════════════════════════

AEGIS_INIT_ANCHOR = (
    "        with sqlite3.connect(self._path) as conn:\n"
    "            conn.executescript(\"\"\"\n"
)
AEGIS_INIT_NEW = (
    "        with sqlite3.connect(self._path) as conn:\n"
    f'            conn.execute("PRAGMA busy_timeout = 5000")  # {MARK}\n'
    "            conn.executescript(\"\"\"\n"
)

AEGIS_CONN_ANCHOR = (
    '        conn = sqlite3.connect(self._path, isolation_level="IMMEDIATE")\n'
    "        try:\n"
)
AEGIS_CONN_NEW = (
    '        conn = sqlite3.connect(self._path, isolation_level="IMMEDIATE")\n'
    f'        conn.execute("PRAGMA busy_timeout = 5000")  # {MARK}\n'
    '        conn.execute("PRAGMA journal_mode = WAL")\n'
    '        conn.execute("PRAGMA synchronous = NORMAL")\n'
    "        try:\n"
)


def patch_aegis(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, AEGIS_INIT_ANCHOR, AEGIS_INIT_NEW, label="aegis _init_db anchor")
    text = _replace_once(text, AEGIS_CONN_ANCHOR, AEGIS_CONN_NEW, label="aegis _conn anchor")
    return text, True
