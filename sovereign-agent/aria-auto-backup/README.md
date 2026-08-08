# aria-auto-backup

Backups that happen without being asked — Gym round #3, the single
highest-leverage resilience item found by the 2026-07-04 gym-round research.

## The gap

`backup.py::snapshot()` was excellent (SHA-256 manifest, online SQLite
backup, never-zero-backups pruning, Tier-3 gated restore) but
**operator-invoked only** — nothing ever triggered it automatically.
atoms.db holds the `lessons` table and the honor ledger: corruption without
a recent manual snapshot meant permanent loss of her memories. Separately
(GAP 4 from the same research): only atoms.db/events.db got the
crash-consistent online-backup treatment — palace.db, shards, persistence,
feedback, and aegis DBs were `shutil.copy2`'d, so a snapshot taken mid-write
could bake a torn DB into the backup itself.

## The fix

1. **`BackupSentinel`** (new, `@register_sentinel`, kill switch
   `SOV_NO_BACKUP_SENTINEL=1`): `scan()` takes **and verifies** a snapshot
   when the newest one is older than the cadence (default 24h,
   `SOV_BACKUP_CADENCE_HOURS`). This is the one deliberate, plainly-stated
   exception to propose-only: a snapshot is purely additive and protective —
   it never modifies or deletes live state, pruning stays inside backup.py's
   own never-zero-backups policy, and **RESTORE stays Tier-3 human-gated,
   untouched**. `health_status()` is cheap (manifest reads + age math, never
   hashes, never snapshots — proven by a test that monkeypatches
   `backup.snapshot` to raise): ok when fresh, warning past the cadence,
   error past 3× or when the last verify failed.
2. **Backup-root safety rule** ("backups live BESIDE the data_dir they
   protect"): `SOV_BACKUP_ROOT` env override → production data_dir uses
   `default_backup_root()` (so the cadence check sees manual snapshots
   too) → any OTHER data_dir resolves to a sibling of *that* dir. This
   matters because two live tests call `scan_all(tmp_path)` — without this
   rule, every full-suite run would have silently written real ~115MB
   snapshots into the production backup root.
3. **Un-torn snapshots** (backup.py patch): the online-backup special case
   generalizes to EVERY `*.db` under data_dir and config_dir; the copy walk
   skips all `*.db`/`-wal`/`-shm` artifacts (WAL/SHM sidecars pair with a
   specific DB state and would corrupt a restored DB if snapshotted out of
   sync). Proven by a test that plants a non-atoms DB in a subdirectory and
   runs `PRAGMA integrity_check` on every DB inside the snapshot.
4. **The heartbeat** (app.py patch): an hourly cockpit timer +
   module-level-guarded `@work(thread=True)` worker runs
   `sentinel.scan()` when `is_enabled() and overdue()`. Timer-only, never
   eager on mount — the aria-vessel-health discipline, doubly critical here
   since an eager kickoff during a short-lived test cockpit boot would
   write a real snapshot.

## Files

- `payload/src/sovereign_agent/stewardship/backup_sentinel.py` — NEW.
- `patcher.py` — `patch_backup_py()` (2 anchored edits), `patch_app()`
  (3 anchored edits), `patch_stewardship_init()` (registration import).
  All idempotent (`MARK = "auto-backup-d"`).
- `tests/test_patcher.py` — structural tests (14).
- `tests/test_auto_backup.py` — shadow-copy behavior tests (12; staged
  only, never promoted).
- `tests/test_auto_backup_live.py` — the promoted copy (plain imports).
- `apply_auto_backup.sh` — guard → backup → patch → copy payload → tests.

## Verify

```
.venv/bin/python -m pytest aria-auto-backup/tests/test_patcher.py \
  aria-auto-backup/tests/test_auto_backup.py -q
```

## Apply

```
./aria-auto-backup/apply_auto_backup.sh
```

Reversible: restore `backup.py`, `cockpit/app.py`,
`stewardship/__init__.py` from the timestamped `backups/` dir and remove
`stewardship/backup_sentinel.py`.
