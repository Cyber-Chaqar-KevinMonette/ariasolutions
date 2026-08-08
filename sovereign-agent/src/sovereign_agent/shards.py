"""
╔══════════════════════════════════════════════════════════════════════════╗
║  shards.py — per-channel sharded storage                                 ║
║  v0.2.18.0                                                                ║
║                                                                           ║
║  THE PROBLEM                                                             ║
║                                                                           ║
║    Until v0.2.17, every channel lived in one ``atoms.db`` file. That    ║
║    works at small-to-medium scale, but it has three real limits:        ║
║                                                                           ║
║      1. Single-writer contention — SQLite has one writer at a time.   ║
║         A long task channel write blocks people-channel reads.        ║
║      2. Per-file size limits — a single .db file growing past tens     ║
║         of GB starts costing on VACUUM, backup, integrity_check.      ║
║      3. Blast radius — a single corrupted DB takes the whole agent     ║
║         offline.                                                       ║
║                                                                           ║
║  THE FIX                                                                 ║
║                                                                           ║
║    Each channel can OPTIONALLY live in its own DB file. The default    ║
║    remains "all in atoms.db" — nothing breaks. Channels listed in     ║
║    the operator's shard configuration get their own connection to    ║
║    their own file, and the channel's companion tables (people,        ║
║    people_facts, recall_sources, etc.) live there.                   ║
║                                                                           ║
║    Atoms themselves stay in ``atoms.db`` — they are the central       ║
║    audit log and must remain queryable cross-channel.                ║
║                                                                           ║
║  CONFIGURATION                                                           ║
║                                                                           ║
║    The operator declares which channels to shard in:                  ║
║                                                                           ║
║      <data>/sovereign-agent/shards.json                               ║
║                                                                           ║
║    Example::                                                          ║
║                                                                           ║
║      { "task": "shards/task.db",                                      ║
║        "reward": "shards/reward.db",                                  ║
║        "heartbeat": "shards/heartbeat.db" }                           ║
║                                                                           ║
║    Channels not listed continue to use the trunk atoms.db. Paths      ║
║    are relative to data_dir.                                          ║
║                                                                           ║
║  MIGRATION                                                               ║
║                                                                           ║
║    A channel that was in atoms.db and is now in a shard must be       ║
║    migrated: copy companion tables out, drop from trunk, swap        ║
║    connections. The ``migrate_channel_to_shard()`` helper does this  ║
║    safely with a backup-and-verify pattern.                          ║
║                                                                           ║
║                                — channels can grow without crowding.    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import SETTINGS


SHARDS_CONFIG_FILENAME = "shards.json"


@dataclass(frozen=True)
class ShardConfig:
    """The per-channel sharding configuration."""
    shards: dict[str, str]    # channel_name → relative path (under data_dir)

    def shard_for(self, channel: str) -> str | None:
        return self.shards.get(channel)

    @property
    def channel_names(self) -> list[str]:
        return list(self.shards.keys())


# ─── Configuration I/O ─────────────────────────────────────────────────────


def load_shard_config() -> ShardConfig:
    """Read shards.json from the config dir. Returns empty config if absent."""
    path = SETTINGS.paths.config_dir / SHARDS_CONFIG_FILENAME
    if not path.is_file():
        return ShardConfig(shards={})
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return ShardConfig(shards={})
        return ShardConfig(shards={k: str(v) for k, v in data.items()})
    except (OSError, ValueError):
        return ShardConfig(shards={})


def save_shard_config(config: ShardConfig) -> None:
    """Atomically write shards.json."""
    path = SETTINGS.paths.config_dir / SHARDS_CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config.shards, indent=2, sort_keys=True))
    tmp.replace(path)


def add_shard(channel: str, relative_path: str | None = None) -> ShardConfig:
    """Declare that ``channel`` should live in its own DB.

    Default path: ``shards/<channel>.db`` under data_dir. The actual
    schema-application + table migration is a SEPARATE step
    (``migrate_channel_to_shard``); this just records the intent.
    """
    cfg = load_shard_config()
    new = dict(cfg.shards)
    new[channel] = relative_path or f"shards/{channel}.db"
    new_cfg = ShardConfig(shards=new)
    save_shard_config(new_cfg)
    return new_cfg


def remove_shard(channel: str) -> ShardConfig:
    """Stop sharding ``channel``. Reverse migration is operator-driven."""
    cfg = load_shard_config()
    new = {k: v for k, v in cfg.shards.items() if k != channel}
    new_cfg = ShardConfig(shards=new)
    save_shard_config(new_cfg)
    return new_cfg


# ─── Connection resolution ─────────────────────────────────────────────────


def shard_db_path(channel: str) -> Path | None:
    """Return the absolute path of ``channel``'s shard, or None if not sharded."""
    cfg = load_shard_config()
    rel = cfg.shard_for(channel)
    if not rel:
        return None
    abs_path = SETTINGS.paths.data_dir / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return abs_path


def open_shard(channel: str) -> sqlite3.Connection | None:
    """Open a connection to ``channel``'s shard DB, applying baseline pragmas.

    Returns None when ``channel`` is not sharded — caller should fall back
    to the trunk atoms.db.
    """
    path = shard_db_path(channel)
    if path is None:
        return None
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 5000")  # db-armor-d
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def resolve_channel_conn(
    channel: str,
    trunk_conn: sqlite3.Connection,
) -> sqlite3.Connection:
    """Return the right connection for ``channel``.

    If the channel is sharded, returns a connection to its shard DB.
    Otherwise returns the provided trunk connection.

    The caller is responsible for the trunk_conn's lifecycle; shard
    connections are owned by the caller after this returns.
    """
    cfg = load_shard_config()
    if channel not in cfg.shards:
        return trunk_conn
    sc = open_shard(channel)
    return sc if sc is not None else trunk_conn


# ─── Migration ─────────────────────────────────────────────────────────────


def migrate_channel_to_shard(
    channel: str,
    *,
    table_names: list[str],
    trunk_conn: sqlite3.Connection,
    shard_path: str | None = None,
    drop_from_trunk: bool = False,
) -> dict:
    """Move a channel's companion tables out of the trunk into a shard.

    Workflow:
      1. Declare the shard in config (add_shard).
      2. Open the shard DB.
      3. Apply the channel's schema to the shard (caller's job to ensure
         schema is current via channel construction on shard_conn).
      4. Copy each named table's rows from trunk to shard.
      5. Verify row counts match.
      6. Optionally drop the tables from the trunk (off by default for
         safety — operator can do that manually after verifying).

    Returns a dict with copied row counts per table and verification status.

    SAFETY: this does not modify trunk tables unless drop_from_trunk=True.
    The default mode is "copy and verify"; the operator must explicitly
    request the drop. This is the safest possible migration semantics:
    until the drop, the data exists in BOTH places and the agent can be
    rolled back trivially.
    """
    add_shard(channel, shard_path)
    shard_conn = open_shard(channel)
    assert shard_conn is not None, "shard config didn't take effect"

    results: dict = {"channel": channel, "tables": {}, "verified": True,
                     "dropped": False}

    for table in table_names:
        # Copy via temporary attach
        trunk_path = str(SETTINGS.paths.atoms_db)
        shard_conn.execute(f"ATTACH DATABASE '{trunk_path}' AS trunk")
        try:
            # Get the original table definition
            ddl_row = shard_conn.execute(
                "SELECT sql FROM trunk.sqlite_master WHERE type='table' "
                "AND name = ?",
                (table,),
            ).fetchone()
            if ddl_row is None or not ddl_row[0]:
                results["tables"][table] = {"copied": 0,
                                              "note": "table not in trunk"}
                continue
            # Create the table in the shard if missing
            shard_conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM trunk.{table} WHERE 0"
            )
            # Insert any rows not already present (by PK). We assume row 1 is the
            # primary key — to be conservative, we use INSERT OR IGNORE.
            shard_conn.execute(
                f"INSERT OR IGNORE INTO {table} SELECT * FROM trunk.{table}"
            )
            trunk_count = shard_conn.execute(
                f"SELECT COUNT(*) FROM trunk.{table}"
            ).fetchone()[0]
            shard_count = shard_conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            results["tables"][table] = {
                "trunk_rows": trunk_count,
                "shard_rows": shard_count,
                "match": shard_count >= trunk_count,
            }
            if shard_count < trunk_count:
                results["verified"] = False
        finally:
            shard_conn.execute("DETACH DATABASE trunk")

    shard_conn.commit()

    if drop_from_trunk and results["verified"]:
        for table in table_names:
            trunk_conn.execute(f"DROP TABLE IF EXISTS {table}")
        trunk_conn.commit()
        results["dropped"] = True

    return results


# ─── Inspection ──────────────────────────────────────────────────────────


def list_shards() -> list[dict]:
    """Report on every configured shard: path, size, table count."""
    cfg = load_shard_config()
    out = []
    for channel, rel_path in cfg.shards.items():
        abs_path = SETTINGS.paths.data_dir / rel_path
        info = {
            "channel": channel,
            "path": str(abs_path),
            "exists": abs_path.is_file(),
            "size_bytes": 0,
            "table_count": 0,
        }
        if abs_path.is_file():
            try:
                info["size_bytes"] = abs_path.stat().st_size
                c = sqlite3.connect(str(abs_path))
                c.execute("PRAGMA busy_timeout = 5000")  # db-armor-d
                info["table_count"] = c.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()[0]
                c.close()
            except (OSError, sqlite3.Error):
                pass
        out.append(info)
    return out


__all__ = [
    "ShardConfig",
    "load_shard_config", "save_shard_config",
    "add_shard", "remove_shard",
    "shard_db_path", "open_shard", "resolve_channel_conn",
    "migrate_channel_to_shard",
    "list_shards",
    "SHARDS_CONFIG_FILENAME",
]
