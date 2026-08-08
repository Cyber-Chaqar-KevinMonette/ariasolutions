# aria-db-armor

Uniform SQLite hardening — Gym round #4.

## The gap

atoms.db and events.db carry the proven pragma block (`db.py:19-22`: WAL +
`synchronous=NORMAL` + `busy_timeout=5000`). Five other stores were missing
some or all of it, so a concurrent cockpit + `sov` CLI + agent subprocess
could intermittently throw `database is locked`:

| Store | Had WAL? | Had busy_timeout? |
|---|---|---|
| `palace.py` | yes (schema) | **no** |
| `shards.py` | yes | **no** |
| `persistence/store.py` (sessions/projects/clock/workflow) | yes (schema) | **no** — the weakest |
| `feedback/feedback.py` (4 bare connect sites) | **no** | **no** |
| `aegis/bitemporal.py` | **no** | **no** |

`busy_timeout` is **per-connection** (unlike WAL, which persists in the DB
file), which is why every patch lands at a connect site, not in schema SQL.

## The fix

Anchored, idempotent patches (`MARK = "db-armor-d"`) adding
`busy_timeout=5000` (+ `synchronous=NORMAL`, + WAL where missing) at each
connect site. `feedback.py` gets one new `_connect()` helper carrying the
full block, with its 4 identical bare sites routed through it.

Proven by `tests/test_db_armor_live.py`: PRAGMA assertions per store, plus
the real-world collision test — a second connection holding a write
transaction while the persistence store writes; without `busy_timeout`
that raises `sqlite3.OperationalError: database is locked` immediately,
with it the write waits and succeeds.

## Verify / Apply

```
.venv/bin/python -m pytest aria-db-armor/tests/test_patcher.py -q
./aria-db-armor/apply_db_armor.sh
```

Reversible: restore the 5 files from the timestamped `backups/` dir.
