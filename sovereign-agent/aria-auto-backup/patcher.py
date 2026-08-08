"""patcher.py — Workstream Gym #3: aria-auto-backup.

Three anchored, idempotent patch targets:
  1. backup.py — (a) `_copy_tree_excluding` skips ALL SQLite artifacts
     (any `*.db` plus `-wal`/`-shm` sidecars), not just atoms/events;
     (b) snapshot()'s online-backup block becomes a loop over EVERY *.db
     under data_dir (and config_dir), so palace.db / shards / persistence /
     feedback / aegis can never be baked into a snapshot torn.
  2. cockpit/app.py — an hourly timer + background worker (module-level
     lock/flag, @work(thread=True), timer-only never-on-mount — the exact
     aria-vessel-health discipline) that runs BackupSentinel.scan() when
     the newest snapshot is older than the cadence. Timer-only matters
     doubly here: a short-lived test cockpit boot must never write a
     snapshot.
  3. stewardship/__init__.py — registration import for backup_sentinel.

backup_sentinel.py itself is a NEW file (payload/), copied whole by the
apply script.
"""
from __future__ import annotations

MARK = "auto-backup-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# backup.py — un-torn snapshots for every SQLite DB
# ═══════════════════════════════════════════════════════════════════════

COPY_TREE_ANCHOR = (
    "    for src_path in _walk_files(src):\n"
    "        if src_path.name in SQLITE_FILES:\n"
    "            continue\n"
)
COPY_TREE_NEW = (
    "    for src_path in _walk_files(src):\n"
    f"        # {MARK}: skip ALL SQLite artifacts (any *.db plus WAL/SHM\n"
    "        # sidecars), not just atoms/events — every .db goes through the\n"
    "        # online-backup API instead; -wal/-shm must never be copied at\n"
    "        # all (they pair with a specific DB state and would corrupt the\n"
    "        # restored DB if snapshotted out of sync with it).\n"
    "        n = src_path.name\n"
    '        if n.endswith(".db") or n.endswith(".db-wal") or n.endswith(".db-shm"):\n'
    "            continue\n"
)

ONLINE_BACKUP_ANCHOR = (
    "        # ── SQLite online backup ──────────────────────────────────────\n"
    '        atoms_db = data_dir / "atoms.db"\n'
    '        events_db = data_dir / "events.db"\n'
    "        bytes_atoms = _online_backup_sqlite(\n"
    '            atoms_db, partial_dir / "data" / "atoms.db",\n'
    "        )\n"
    "        bytes_events = _online_backup_sqlite(\n"
    '            events_db, partial_dir / "data" / "events.db",\n'
    "        )\n"
)
ONLINE_BACKUP_NEW = (
    f"        # ── SQLite online backup ── {MARK}\n"
    "        # EVERY *.db under the data/config trees gets the crash-consistent\n"
    "        # online-backup treatment — not just atoms/events. A plain copy2\n"
    "        # of a live SQLite file (palace.db, shards, persistence, feedback,\n"
    "        # aegis...) can bake a torn DB into the snapshot.\n"
    '        atoms_db = data_dir / "atoms.db"\n'
    "        for _db_path in _walk_files(data_dir):\n"
    '            if _db_path.suffix != ".db":\n'
    "                continue\n"
    "            _online_backup_sqlite(\n"
    '                _db_path, partial_dir / "data" / _db_path.relative_to(data_dir),\n'
    "            )\n"
    "        for _db_path in _walk_files(config_dir):\n"
    '            if _db_path.suffix != ".db":\n'
    "                continue\n"
    "            _online_backup_sqlite(\n"
    '                _db_path, partial_dir / "config" / _db_path.relative_to(config_dir),\n'
    "            )\n"
)


def patch_backup_py(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, COPY_TREE_ANCHOR, COPY_TREE_NEW, label="backup.py copy-tree anchor")
    text = _replace_once(text, ONLINE_BACKUP_ANCHOR, ONLINE_BACKUP_NEW, label="backup.py online-backup anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# cockpit/app.py — hourly auto-backup timer + worker
# ═══════════════════════════════════════════════════════════════════════

APP_FLAGS_ANCHOR = (
    "_VESSEL_KERNEL_LOCK = threading.Lock()\n"
    "_VESSEL_KERNEL_RUNNING = False\n"
)
APP_FLAGS_NEW = (
    "_VESSEL_KERNEL_LOCK = threading.Lock()\n"
    "_VESSEL_KERNEL_RUNNING = False\n"
    f"_AUTO_BACKUP_LOCK = threading.Lock()  # {MARK}\n"
    f"_AUTO_BACKUP_RUNNING = False  # {MARK}\n"
)

APP_TIMER_ANCHOR = (
    "        self.set_interval(300.0, self._maybe_run_vessel_kernel_scan)\n"
)
APP_TIMER_NEW = (
    "        self.set_interval(300.0, self._maybe_run_vessel_kernel_scan)\n"
    f"        self.set_interval(3600.0, self._maybe_run_auto_backup)  # {MARK}\n"
)

APP_METHODS_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
APP_METHODS_NEW = (
    f"    def _maybe_run_auto_backup(self) -> None:  # {MARK}\n"
    '        """Hourly check: if the newest snapshot is older than the cadence,\n'
    "        kick a background snapshot via BackupSentinel.scan(). Timer-only —\n"
    "        never called on mount (a short-lived test cockpit boot must never\n"
    '        write a snapshot; same discipline as the vessel kernel scan)."""\n'
    "        global _AUTO_BACKUP_RUNNING\n"
    "        with _AUTO_BACKUP_LOCK:\n"
    "            if _AUTO_BACKUP_RUNNING:\n"
    "                return\n"
    "            _AUTO_BACKUP_RUNNING = True\n"
    "        self._run_auto_backup_worker()\n"
    "\n"
    f'    @work(exclusive=True, group="auto-backup", thread=True)  # {MARK}\n'
    "    def _run_auto_backup_worker(self) -> None:\n"
    '        """Snapshot + verify off the main thread. The sentinel no-ops\n'
    '        when a fresh-enough snapshot already exists (overdue() check)."""\n'
    "        global _AUTO_BACKUP_RUNNING\n"
    "        try:\n"
    "            from sovereign_agent.config import SETTINGS\n"
    "            from sovereign_agent.stewardship.backup_sentinel import BackupSentinel\n"
    "\n"
    "            sentinel = BackupSentinel(data_dir=SETTINGS.paths.data_dir)\n"
    "            if sentinel.is_enabled() and sentinel.overdue():\n"
    "                sentinel.scan()\n"
    "        except Exception:  # noqa: BLE001 — backup failure must never hurt the cockpit\n"
    "            pass\n"
    "        finally:\n"
    "            with _AUTO_BACKUP_LOCK:\n"
    "                _AUTO_BACKUP_RUNNING = False\n"
    "\n"
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, APP_FLAGS_ANCHOR, APP_FLAGS_NEW, label="app.py module flags anchor")
    text = _replace_once(text, APP_TIMER_ANCHOR, APP_TIMER_NEW, label="app.py timer anchor")
    text = _replace_once(text, APP_METHODS_ANCHOR, APP_METHODS_NEW, label="app.py methods anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# stewardship/__init__.py — register the module (import for side effect)
# ═══════════════════════════════════════════════════════════════════════

STEWARDSHIP_INIT_ANCHOR = (
    "from . import glyph_sentinel as _glyph_sentinel  # noqa: F401  # glyph-sentinel-migration-d\n"
)
STEWARDSHIP_INIT_NEW = (
    STEWARDSHIP_INIT_ANCHOR
    + f"from . import backup_sentinel as _backup_sentinel  # noqa: F401  # {MARK}\n"
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(
        text, STEWARDSHIP_INIT_ANCHOR, STEWARDSHIP_INIT_NEW, label="stewardship init anchor"
    )
    return text, True
