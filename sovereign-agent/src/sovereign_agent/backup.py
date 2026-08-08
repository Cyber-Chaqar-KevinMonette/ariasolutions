"""
╔══════════════════════════════════════════════════════════════════════════╗
║  backup.py — Application-aware backup/restore for sovereign-agent       ║
║  v0.2.14.2 · Aria-Sovereign-V1                                           ║
║                                                                           ║
║  The previous "backup" was a shell function that did `cp -r` of the      ║
║  data dir. That violates this system's own doctrine:                     ║
║                                                                           ║
║    • cp -r of an active SQLite DB produces torn reads (no online-backup) ║
║    • No verification — bit-rot would only surface at restore time        ║
║    • No retention — snapshots accumulate forever                         ║
║    • No restore tool — "manually cp -r back" is not a rollback path     ║
║    • No authority tier — restore is the most destructive op in the       ║
║      whole system but had no confirmation gate                           ║
║                                                                           ║
║  This module is the doctrine-aligned replacement. It uses:               ║
║                                                                           ║
║    • SQLite Connection.backup() for atoms.db / events.db (§16 atomicity) ║
║    • Per-file SHA-256 with tamper-detected manifest (§17 observability)  ║
║    • Authority Tier 3 on restore with PROTOCOL-ZERO during the swap     ║
║    • Append-only snapshot directories — restore never deletes, it       ║
║      auto-snapshots current state first (rollback-of-rollback)          ║
║    • A "never zero backups" invariant in pruning                        ║
║    • Application-level audit (financial.audit()) on staged DBs before   ║
║      they overwrite live data                                            ║
║                                                                           ║
║  STORAGE LAYOUT                                                           ║
║                                                                           ║
║    <backup_root>/                                                        ║
║      snap-2026-05-10T17-55-00Z-abc12345/                                ║
║        MANIFEST.json          # SnapshotManifest serialized              ║
║        MANIFEST.sha256        # hash of MANIFEST.json (tamper detect)    ║
║        data/                                                             ║
║          atoms.db             # via SQLite online backup                ║
║          events/...                                                      ║
║          ...                                                             ║
║        config/                                                           ║
║          ...                                                             ║
║                                                                           ║
║  AUTHORITY TIERS                                                          ║
║    snapshot()       Tier 2 — persistent change, external location        ║
║    list_snapshots() Tier 0 — read-only                                   ║
║    verify()         Tier 0 — read-only                                   ║
║    status()         Tier 0 — read-only                                   ║
║    prune()          Tier 2 — persistent change, but bounded by policy    ║
║    restore()        Tier 3 — irreversible swap; CLI confirmation        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

# ─── Constants ──────────────────────────────────────────────────────────────


SNAPSHOT_PREFIX = "snap-"
MANIFEST_FILENAME = "MANIFEST.json"
MANIFEST_HASH_FILENAME = "MANIFEST.sha256"
EXCLUDED_PATTERNS = (
    "venv",                 # Python venvs that may live inside data dir
    "__pycache__",
    ".pytest_cache",
    ".restore-staging",     # never recurse into our own staging dir
    "sandbox",              # ephemeral agent scratch (broken symlinks
                            # for sandbox-escape tests, transient state);
                            # restoring it would re-introduce stale test
                            # artifacts. Real persistent state lives in
                            # atoms.db / events.db / blobs.
                            #
                            # EXCEPT sandbox/games/ (carved out below,
                            # found live 2026-08-03): game_workspace_dir()
                            # puts every real game project under
                            # sandbox_dir/games/<slug> — a blanket
                            # exclusion silently meant zero backup
                            # coverage for Aria's actual creative work,
                            # not just ephemeral scratch.
)
# Files whose hashes we recompute on verify regardless of size.
# Everything is hashed; this is just a hint for future selective behavior.
SQLITE_FILES = ("atoms.db", "events.db")

# Idempotency window: snapshots within this many seconds of an unlabeled
# previous snapshot return the previous one rather than re-running.
SNAPSHOT_IDEMPOTENCY_WINDOW_SECONDS = 60


# ─── Errors ─────────────────────────────────────────────────────────────────


class BackupError(Exception):
    """Base class for backup-system errors."""


class SnapshotNotFoundError(BackupError):
    """Raised when a snapshot id can't be resolved."""


class SnapshotCorruptError(BackupError):
    """Raised when a snapshot fails verification."""


class RestoreRefusedError(BackupError):
    """Raised when restore aborts due to a pre-restore audit failure."""


# ─── Data classes ───────────────────────────────────────────────────────────


@dataclass
class FileEntry:
    """One file's record in the snapshot manifest."""
    path: str            # relative to snapshot root
    bytes: int
    sha256: str


@dataclass
class SnapshotManifest:
    """Everything the backup system promises about a snapshot."""
    snapshot_id: str
    created_at: str                   # ISO 8601 UTC
    label: str                        # operator-supplied tag, may be ''
    source_version: str
    source_data_dir: str
    source_config_dir: str
    total_bytes: int
    file_count: int
    files: list[FileEntry]
    excluded_patterns: list[str]
    atoms_count: int
    events_count: int
    financial_ledger_count: int
    audit_at_snapshot: dict           # FinancialChannel.audit() result snapshot
    schema_version: int = 1

    def to_json(self) -> str:
        """Stable JSON serialization (sorted keys)."""
        d = asdict(self)
        # FileEntry list serialises automatically via asdict.
        return json.dumps(d, sort_keys=True, indent=2)


@dataclass
class VerifyResult:
    """Result of verifying a single snapshot."""
    snapshot_id: str
    ok: bool
    manifest_hash_ok: bool
    file_count_expected: int
    file_count_found: int
    mismatched_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    extra_files: list[str] = field(default_factory=list)
    audit_clean: bool = True
    audit_violations: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class PruneResult:
    """Result of running the retention policy."""
    kept: list[str]
    removed: list[str]
    bytes_freed: int
    dry_run: bool


@dataclass
class RestoreResult:
    """Result of a restore operation."""
    snapshot_id: str
    pre_restore_snapshot_id: str
    restored_at: str
    staged_audit_clean: bool


@dataclass
class BackupStatus:
    """Single-screen view of the backup state."""
    backup_root: str
    snapshot_count: int
    total_bytes: int
    most_recent_snapshot_id: Optional[str]
    most_recent_age_seconds: Optional[float]
    oldest_snapshot_id: Optional[str]
    last_verify_ok: Optional[bool]


# ─── Path discovery ─────────────────────────────────────────────────────────


def default_backup_root() -> Path:
    """Default backup destination: ~/AA-Erebo/sov-backups, falling back to
    a sibling of the data dir (NOT inside it).

    The "sibling not child" rule matters because restore atomically
    replaces the data dir; snapshots stored inside the data dir would
    be obliterated by their own restore. The fallback computes
    ``<data_dir>.parent / "sovereign-agent-backups"`` so the backup
    tree survives any restore of the data tree.
    """
    aa_erebo = Path.home() / "AA-Erebo" / "sov-backups"
    if aa_erebo.parent.exists():
        return aa_erebo
    from .config import SETTINGS
    # SIBLING of data_dir — never a child. Restore would otherwise eat
    # the very snapshots that prove it happened.
    return SETTINGS.paths.data_dir.parent / "sovereign-agent-backups"


def _validate_backup_root(
    backup_root: Path, data_dir: Path, config_dir: Path,
) -> None:
    """Refuse a backup_root that lives inside data_dir or config_dir.

    A nested backup root is a circular-dependency landmine: snapshot
    builds a partial directory inside the very tree it's copying;
    restore replaces the data dir and destroys all snapshots in the
    process. Defence-in-depth: even if a future caller ignores the
    sensible default, we won't let them shoot themselves.
    """
    backup_root = backup_root.resolve()
    for parent in (data_dir.resolve(), config_dir.resolve()):
        try:
            backup_root.relative_to(parent)
        except ValueError:
            continue
        # backup_root IS inside parent — refuse.
        raise BackupError(
            f"backup_root {backup_root} is inside {parent}; refusing. "
            f"Place backup_root outside the data and config trees so "
            f"restore cannot destroy its own snapshots."
        )


# ─── Snapshot id minting ────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _now_id_safe() -> str:
    """Filesystem-safe timestamp for snapshot ids: YYYY-MM-DDTHH-MM-SSZ."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _mint_snapshot_id(label: str = "") -> str:
    """``snap-<UTC>-<random8>``. Random suffix avoids collisions on the
    sub-second scale even though the timestamp is second-resolution."""
    import secrets
    suffix = secrets.token_hex(4)
    base = f"{SNAPSHOT_PREFIX}{_now_id_safe()}-{suffix}"
    if label:
        # Sanitise: only alnum + dash + underscore in labels.
        safe_label = re.sub(r"[^A-Za-z0-9_-]", "-", label)[:40]
        base = f"{base}-{safe_label}"
    return base


# ─── Core hashing ───────────────────────────────────────────────────────────


def _sha256_file(path: Path, *, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ─── Exclusion ──────────────────────────────────────────────────────────────


def _is_excluded(path: Path, base: Path) -> bool:
    """True if ``path`` (under ``base``) matches any excluded pattern.

    Matched by scanning for "sandbox" at ANY depth, not a fixed prefix
    position — this walk runs against multiple bases (data_dir directly,
    and later a snapshot's partial_dir where "sandbox" sits one level
    deeper under "data/"), so a fixed-position prefix check silently
    missed the games/ carve-out at the deeper base (found live
    2026-08-03).
    """
    try:
        rel = path.relative_to(base)
    except ValueError:
        return False
    parts = rel.parts
    for i, part in enumerate(parts):
        if part == "sandbox" and parts[i + 1 : i + 2] == ("games",):
            continue  # real game-project files — must be backed up
        if part in EXCLUDED_PATTERNS:
            return True
    return False


# ─── Walk and copy with exclusions ──────────────────────────────────────────


def _walk_files(base: Path) -> Iterator[Path]:
    """Yield every file under ``base`` honoring EXCLUDED_PATTERNS."""
    if not base.exists():
        return
    for root, dirs, files in os.walk(base):
        root_path = Path(root)
        if root_path.name == "sandbox":
            # Don't prune "games" here — it's the one sandbox subtree
            # that must still be walked (see _is_excluded's matching "sandbox"/"games" carve-out).
            # Matched by name, not full relative path, because this walk
            # runs against multiple bases (data_dir directly, and later
            # a snapshot's partial_dir where "sandbox" sits one level
            # deeper under "data/") — found live 2026-08-03 when the
            # manifest-hashing pass (base=partial_dir) missed sandbox/
            # games entirely despite the copy pass (base=data_dir)
            # having already copied them correctly.
            dirs[:] = [d for d in dirs if d == "games"]
        else:
            # Prune excluded subdirs in-place so os.walk doesn't recurse
            # into them — EXCEPT never prune "sandbox" itself here.
            # os.walk prunes at the PARENT's dirs list, so a flat
            # "d not in EXCLUDED_PATTERNS" would drop "sandbox" before
            # os.walk ever got a chance to descend into it and hit the
            # games/ carve-out above (found live 2026-08-03).
            dirs[:] = [d for d in dirs if d not in EXCLUDED_PATTERNS or d == "sandbox"]
        for fn in files:
            fp = root_path / fn
            if _is_excluded(fp, base):
                continue
            # Defensive: skip non-regular files (broken symlinks, sockets,
            # FIFOs, dangling test artifacts). os.walk yields these but
            # we can't hash them and stat() raises FileNotFoundError on
            # broken symlinks. Belt-and-suspenders with EXCLUDED_PATTERNS:
            # even if a future scratch dir misses the exclusion list,
            # backups don't crash on file-system weirdness inside it.
            try:
                if not fp.is_file():
                    continue
            except OSError:
                continue
            yield fp


def _copy_tree_excluding(src: Path, dst: Path) -> int:
    """Copy ``src`` to ``dst`` honoring exclusions. Returns bytes copied.

    Skips SQLite DBs — those go through online backup separately.
    """
    bytes_copied = 0
    for src_path in _walk_files(src):
        # auto-backup-d: skip ALL SQLite artifacts (any *.db plus WAL/SHM
        # sidecars), not just atoms/events — every .db goes through the
        # online-backup API instead; -wal/-shm must never be copied at
        # all (they pair with a specific DB state and would corrupt the
        # restored DB if snapshotted out of sync with it).
        n = src_path.name
        if n.endswith(".db") or n.endswith(".db-wal") or n.endswith(".db-shm"):
            continue
        rel = src_path.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, out)
        bytes_copied += out.stat().st_size
    return bytes_copied


# ─── SQLite online backup ───────────────────────────────────────────────────


def _online_backup_sqlite(src_db: Path, dst_db: Path) -> int:
    """Use SQLite's online backup API for crash-consistent copy.

    This is application-consistent — the destination DB sees a coherent
    snapshot even if the source is being written to concurrently. The
    `cp -r` approach we replaced could not promise this.
    """
    if not src_db.exists():
        return 0
    dst_db.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src_db))
    try:
        dst_conn = sqlite3.connect(str(dst_db))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return dst_db.stat().st_size


# ─── Snapshot ───────────────────────────────────────────────────────────────


def _atoms_audit_snapshot(atoms_db: Path) -> tuple[dict, int, int, int]:
    """Open atoms.db read-only, run audit, return (audit_dict, atoms_count,
    events_count, ledger_count). Each count defaults to 0 if its table is
    absent (e.g. fresh install)."""
    if not atoms_db.exists():
        return ({"ok": True, "ledger_rows": 0, "violations": []}, 0, 0, 0)

    # Open read-only. URI form lets us pin mode=ro.
    uri = f"file:{atoms_db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        atoms_n = events_n = ledger_n = 0
        try:
            atoms_n = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
        except sqlite3.OperationalError:
            pass
        try:
            events_n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        except sqlite3.OperationalError:
            pass
        try:
            ledger_n = conn.execute(
                "SELECT COUNT(*) FROM financial_ledger"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass

        # Audit if the ledger table exists.
        audit_dict: dict = {"ok": True, "ledger_rows": ledger_n,
                            "violations": []}
        if ledger_n > 0:
            try:
                from .mem_channels.financial import FinancialChannel
                # FinancialChannel needs a writable conn for ensure_ledger_schema
                # but we already know the ledger exists. Open a fresh writable
                # connection only for the audit.
                conn.close()
                conn = sqlite3.connect(str(atoms_db))
                fc = FinancialChannel(conn)
                result = fc.audit()
                audit_dict = {
                    "ok": result.ok,
                    "ledger_rows": result.ledger_rows,
                    "violations": result.violations,
                }
            except Exception as exc:  # noqa: BLE001
                audit_dict = {"ok": False, "ledger_rows": ledger_n,
                              "violations": [f"audit-failed: {exc!r}"]}

        return (audit_dict, atoms_n, events_n, ledger_n)
    finally:
        conn.close()


def snapshot(
    *,
    backup_root: Optional[Path] = None,
    label: str = "",
    data_dir: Optional[Path] = None,
    config_dir: Optional[Path] = None,
) -> SnapshotManifest:
    """Capture a snapshot. Tier 2.

    The atoms.db and events.db are copied via SQLite's online backup API
    so the result is crash-consistent even if writers are active. All
    other files are copied via shutil.copy2 with EXCLUDED_PATTERNS
    pruned (venv, __pycache__, etc).

    Idempotency: if an unlabeled snapshot was created within
    SNAPSHOT_IDEMPOTENCY_WINDOW_SECONDS and ``label`` is empty, this
    returns the previous one without re-snapshotting.

    Args:
        backup_root: where snapshots live. Defaults to
            ~/AA-Erebo/sov-backups or, if that tree doesn't exist,
            ``data_dir/backups``.
        label: optional operator tag. Sanitised to [A-Za-z0-9_-]{0,40}.
        data_dir / config_dir: source paths. Default to SETTINGS.paths.

    Returns:
        SnapshotManifest of the new (or re-used) snapshot.
    """
    from .config import SETTINGS

    backup_root = backup_root or default_backup_root()
    data_dir = data_dir or SETTINGS.paths.data_dir
    config_dir = config_dir or SETTINGS.paths.config_dir
    _validate_backup_root(backup_root, data_dir, config_dir)
    backup_root.mkdir(parents=True, exist_ok=True)

    # ── Idempotency check ─────────────────────────────────────────────
    if not label:
        recent = _most_recent_unlabeled_snapshot(
            backup_root, within_seconds=SNAPSHOT_IDEMPOTENCY_WINDOW_SECONDS,
        )
        if recent is not None:
            return recent

    snapshot_id = _mint_snapshot_id(label)
    snapshot_dir = backup_root / snapshot_id

    # Build into a sibling .partial dir, rename atomically when done.
    partial_dir = backup_root / (snapshot_id + ".partial")
    if partial_dir.exists():
        shutil.rmtree(partial_dir)
    (partial_dir / "data").mkdir(parents=True)
    (partial_dir / "config").mkdir(parents=True)

    try:
        # ── Copy non-SQLite data files ────────────────────────────────
        bytes_data = _copy_tree_excluding(data_dir, partial_dir / "data")
        bytes_config = _copy_tree_excluding(config_dir, partial_dir / "config")

        # ── SQLite online backup ── auto-backup-d
        # EVERY *.db under the data/config trees gets the crash-consistent
        # online-backup treatment — not just atoms/events. A plain copy2
        # of a live SQLite file (palace.db, shards, persistence, feedback,
        # aegis...) can bake a torn DB into the snapshot.
        atoms_db = data_dir / "atoms.db"
        for _db_path in _walk_files(data_dir):
            if _db_path.suffix != ".db":
                continue
            _online_backup_sqlite(
                _db_path, partial_dir / "data" / _db_path.relative_to(data_dir),
            )
        for _db_path in _walk_files(config_dir):
            if _db_path.suffix != ".db":
                continue
            _online_backup_sqlite(
                _db_path, partial_dir / "config" / _db_path.relative_to(config_dir),
            )

        # ── Counts and audit ──────────────────────────────────────────
        audit_dict, atoms_n, events_n, ledger_n = _atoms_audit_snapshot(atoms_db)

        # ── Compute file hashes for manifest ─────────────────────────
        files: list[FileEntry] = []
        total_bytes = 0
        for fp in _walk_files(partial_dir):
            if fp.name in (MANIFEST_FILENAME, MANIFEST_HASH_FILENAME):
                continue
            rel = str(fp.relative_to(partial_dir))
            size = fp.stat().st_size
            files.append(FileEntry(
                path=rel, bytes=size, sha256=_sha256_file(fp),
            ))
            total_bytes += size

        # Resolve current installed version (best-effort).
        try:
            from . import __version__ as src_version
        except ImportError:
            src_version = "unknown"

        manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            created_at=_now_iso(),
            label=label,
            source_version=src_version,
            source_data_dir=str(data_dir),
            source_config_dir=str(config_dir),
            total_bytes=total_bytes,
            file_count=len(files),
            files=files,
            excluded_patterns=list(EXCLUDED_PATTERNS),
            atoms_count=atoms_n,
            events_count=events_n,
            financial_ledger_count=ledger_n,
            audit_at_snapshot=audit_dict,
        )

        manifest_json = manifest.to_json()
        (partial_dir / MANIFEST_FILENAME).write_text(manifest_json)
        manifest_hash = _sha256_bytes(manifest_json.encode("utf-8"))
        (partial_dir / MANIFEST_HASH_FILENAME).write_text(manifest_hash + "\n")

        # ── Atomic rename — snapshot becomes visible only when complete ─
        partial_dir.rename(snapshot_dir)

    except Exception:
        # Clean up the partial on any failure.
        if partial_dir.exists():
            shutil.rmtree(partial_dir, ignore_errors=True)
        raise

    # ── Observability ────────────────────────────────────────────────
    try:
        from .events import emit_event
        emit_event(
            "backup-snapshot-d", plane="control",
            trace_id=f"backup:{snapshot_id}",
            payload={
                "snapshot_id": snapshot_id,
                "total_bytes": manifest.total_bytes,
                "file_count": manifest.file_count,
                "atoms_count": manifest.atoms_count,
                "label": label,
                "audit_clean": audit_dict.get("ok", False),
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[backup] event emit failed: {exc!r}", file=sys.stderr)

    return manifest


def _most_recent_unlabeled_snapshot(
    backup_root: Path, *, within_seconds: int,
) -> Optional[SnapshotManifest]:
    """Return the latest unlabeled snapshot if it's within the window."""
    snaps = list_snapshots(backup_root=backup_root)
    if not snaps:
        return None
    latest = snaps[0]  # list_snapshots returns newest-first
    if latest.label:
        return None
    try:
        latest_dt = datetime.strptime(
            latest.created_at, "%Y-%m-%dT%H:%M:%S.%fZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    age = (datetime.now(timezone.utc) - latest_dt).total_seconds()
    if age <= within_seconds:
        return latest
    return None


# ─── List ───────────────────────────────────────────────────────────────────


def list_snapshots(
    *, backup_root: Optional[Path] = None,
) -> list[SnapshotManifest]:
    """All snapshots under ``backup_root``, newest-first. Tier 0."""
    backup_root = backup_root or default_backup_root()
    if not backup_root.exists():
        return []
    out: list[SnapshotManifest] = []
    for child in sorted(backup_root.iterdir(), reverse=True):
        if not child.is_dir() or not child.name.startswith(SNAPSHOT_PREFIX):
            continue
        manifest_path = child / MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text())
            data["files"] = [FileEntry(**f) for f in data.get("files", [])]
            out.append(SnapshotManifest(**data))
        except (json.JSONDecodeError, TypeError, KeyError):
            # Manifest unreadable — skip rather than crash the listing.
            continue
    return out


def _resolve_snapshot(
    snapshot_id: str, *, backup_root: Optional[Path] = None,
) -> tuple[Path, SnapshotManifest]:
    """Resolve a snapshot id to (path, manifest).

    Lookup is forgiving: matches a snapshot if EITHER
      - the snapshot's directory name starts with ``snapshot_id``, OR
      - the snapshot's label equals ``snapshot_id`` exactly.

    Ambiguity raises SnapshotNotFoundError with the candidates listed.
    """
    backup_root = backup_root or default_backup_root()
    if not backup_root.exists():
        raise SnapshotNotFoundError(
            f"backup root {backup_root} does not exist"
        )

    prefix_matches: list[Path] = []
    label_matches: list[Path] = []
    for child in backup_root.iterdir():
        if not child.is_dir() or not child.name.startswith(SNAPSHOT_PREFIX):
            continue
        if child.name.startswith(snapshot_id):
            prefix_matches.append(child)
            continue
        # Try label match: load manifest, compare label.
        manifest_path = child / MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            continue
        if data.get("label") == snapshot_id:
            label_matches.append(child)

    candidates = prefix_matches if prefix_matches else label_matches
    if len(candidates) == 0:
        raise SnapshotNotFoundError(f"no snapshot matching {snapshot_id!r}")
    if len(candidates) > 1:
        raise SnapshotNotFoundError(
            f"snapshot id {snapshot_id!r} ambiguous; "
            f"matches: {[c.name for c in candidates]}"
        )
    snap_path = candidates[0]
    manifest_path = snap_path / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise SnapshotCorruptError(
            f"snapshot {snap_path.name} has no manifest"
        )
    data = json.loads(manifest_path.read_text())
    data["files"] = [FileEntry(**f) for f in data.get("files", [])]
    return snap_path, SnapshotManifest(**data)


# ─── Verify ─────────────────────────────────────────────────────────────────


def verify(
    snapshot_id: str, *, backup_root: Optional[Path] = None,
    run_audit: bool = True,
) -> VerifyResult:
    """Re-hash every file in the snapshot and compare against the manifest.
    Also re-hash the manifest itself against MANIFEST.sha256.

    With ``run_audit=True`` (default), opens the snapshot's atoms.db
    read-only and runs the financial audit on it — catches application-
    level corruption that file hashes alone wouldn't detect.

    Tier 0.
    """
    try:
        snap_path, manifest = _resolve_snapshot(
            snapshot_id, backup_root=backup_root,
        )
    except (SnapshotNotFoundError, SnapshotCorruptError) as exc:
        return VerifyResult(
            snapshot_id=snapshot_id, ok=False,
            manifest_hash_ok=False,
            file_count_expected=0, file_count_found=0,
            error=str(exc),
        )

    # 1. Manifest hash.
    manifest_path = snap_path / MANIFEST_FILENAME
    manifest_hash_path = snap_path / MANIFEST_HASH_FILENAME
    manifest_hash_ok = False
    if manifest_hash_path.exists():
        recorded = manifest_hash_path.read_text().strip()
        actual = _sha256_bytes(manifest_path.read_bytes())
        manifest_hash_ok = (recorded == actual)

    # 2. Per-file hashes.
    expected_paths: dict[str, FileEntry] = {f.path: f for f in manifest.files}
    found_paths: set[str] = set()
    mismatched: list[str] = []

    for fp in _walk_files(snap_path):
        if fp.name in (MANIFEST_FILENAME, MANIFEST_HASH_FILENAME):
            continue
        rel = str(fp.relative_to(snap_path))
        found_paths.add(rel)
        expected = expected_paths.get(rel)
        if expected is None:
            continue  # logged as extra below
        actual_hash = _sha256_file(fp)
        if actual_hash != expected.sha256:
            mismatched.append(rel)

    missing = [p for p in expected_paths if p not in found_paths]
    extra = [p for p in found_paths if p not in expected_paths]

    # 3. Audit the staged atoms.db if requested and present.
    audit_clean = True
    audit_violations: list[str] = []
    if run_audit:
        staged_atoms = snap_path / "data" / "atoms.db"
        if staged_atoms.exists():
            try:
                audit_dict, _, _, _ = _atoms_audit_snapshot(staged_atoms)
                audit_clean = bool(audit_dict.get("ok", False))
                audit_violations = audit_dict.get("violations", [])
            except Exception as exc:  # noqa: BLE001
                audit_clean = False
                audit_violations = [f"audit-error: {exc!r}"]

    ok = (
        manifest_hash_ok
        and not mismatched
        and not missing
        and audit_clean
    )

    return VerifyResult(
        snapshot_id=manifest.snapshot_id,
        ok=ok,
        manifest_hash_ok=manifest_hash_ok,
        file_count_expected=len(expected_paths),
        file_count_found=len(found_paths),
        mismatched_files=mismatched,
        missing_files=missing,
        extra_files=extra,
        audit_clean=audit_clean,
        audit_violations=audit_violations,
    )


# ─── Prune (retention) ──────────────────────────────────────────────────────


@dataclass
class RetentionPolicy:
    """Default retention: keep all <24h, daily up to 7d, weekly up to 30d,
    monthly thereafter. Always keeps the most recent snapshot regardless."""
    keep_all_within_hours: int = 24
    keep_daily_within_days: int = 7
    keep_weekly_within_days: int = 30
    keep_monthly_within_days: int = 365
    keep_labeled_forever: bool = True
    minimum_to_keep: int = 1


def _bucketize(snap: SnapshotManifest, now: datetime) -> tuple:
    """Return a sortable bucket key for retention. Snapshots in the same
    bucket compete; only the newest in each bucket survives."""
    try:
        dt = datetime.strptime(
            snap.created_at, "%Y-%m-%dT%H:%M:%S.%fZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return ("invalid", snap.snapshot_id)
    age = now - dt
    if age <= timedelta(hours=24):
        return ("all", snap.snapshot_id)  # all <24h are kept individually
    if age <= timedelta(days=7):
        return ("daily", dt.strftime("%Y-%m-%d"))
    if age <= timedelta(days=30):
        return ("weekly", dt.strftime("%Y-W%U"))
    if age <= timedelta(days=365):
        return ("monthly", dt.strftime("%Y-%m"))
    return ("yearly", dt.strftime("%Y"))


def prune(
    *, backup_root: Optional[Path] = None,
    policy: Optional[RetentionPolicy] = None,
    dry_run: bool = False,
) -> PruneResult:
    """Apply retention policy. Tier 2.

    Invariant: always keeps the most recent snapshot regardless of policy.
    Labeled snapshots are kept forever by default."""
    backup_root = backup_root or default_backup_root()
    policy = policy or RetentionPolicy()
    snaps = list_snapshots(backup_root=backup_root)
    if len(snaps) <= policy.minimum_to_keep:
        return PruneResult(
            kept=[s.snapshot_id for s in snaps],
            removed=[], bytes_freed=0, dry_run=dry_run,
        )

    now = datetime.now(timezone.utc)
    # Group by bucket; keep newest-per-bucket (and labeled, and "all" bucket).
    seen_buckets: set[tuple] = set()
    to_keep: set[str] = set()
    to_remove: list[SnapshotManifest] = []

    # Always keep the newest (the minimum_to_keep invariant).
    if snaps:
        to_keep.add(snaps[0].snapshot_id)

    for s in snaps:
        if policy.keep_labeled_forever and s.label:
            to_keep.add(s.snapshot_id)
            continue
        bucket = _bucketize(s, now)
        if bucket[0] == "all":
            to_keep.add(s.snapshot_id)
            continue
        if bucket not in seen_buckets:
            to_keep.add(s.snapshot_id)
            seen_buckets.add(bucket)
        else:
            to_remove.append(s)

    bytes_freed = 0
    removed_ids: list[str] = []
    for s in to_remove:
        snap_path = backup_root / s.snapshot_id
        if snap_path.exists():
            size = sum(f.bytes for f in s.files)
            if not dry_run:
                shutil.rmtree(snap_path)
            bytes_freed += size
            removed_ids.append(s.snapshot_id)

    if not dry_run and removed_ids:
        try:
            from .events import emit_event
            emit_event(
                "backup-prune-d", plane="control",
                trace_id="backup:prune",
                payload={
                    "removed_count": len(removed_ids),
                    "bytes_freed": bytes_freed,
                    "kept_count": len(to_keep),
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[backup] prune event emit failed: {exc!r}", file=sys.stderr)

    return PruneResult(
        kept=sorted(to_keep), removed=removed_ids,
        bytes_freed=bytes_freed, dry_run=dry_run,
    )


# ─── Restore ────────────────────────────────────────────────────────────────


def restore(
    snapshot_id: str, *,
    backup_root: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    config_dir: Optional[Path] = None,
    confirmed: bool = False,
) -> RestoreResult:
    """Replace the live data dir with a snapshot. Tier 3.

    The most destructive operation in the system. Multi-stage:

    1. Verify the target snapshot's hashes.
    2. Snapshot the CURRENT live state with label ``pre-restore-...``.
    3. Stage the snapshot data into ``<data_dir>/.restore-staging``.
    4. Run financial.audit() against the staged atoms.db.
    5. If audit clean: arm PROTOCOL-ZERO, swap, disarm with restart hint.
    6. If audit fails: refuse, preserve staging dir for forensics.

    Args:
        confirmed: must be True. The CLI gates this with an interactive
            confirmation prompt; programmatic callers must pass it
            explicitly. False raises ValueError.
    """
    if not confirmed:
        raise ValueError(
            "restore() is Tier 3; pass confirmed=True (CLI handles this)"
        )

    from .config import SETTINGS
    from . import protocol_zero

    backup_root = backup_root or default_backup_root()
    data_dir = data_dir or SETTINGS.paths.data_dir
    config_dir = config_dir or SETTINGS.paths.config_dir
    _validate_backup_root(backup_root, data_dir, config_dir)

    # ── 1. Verify ────────────────────────────────────────────────────
    v = verify(snapshot_id, backup_root=backup_root)
    if not v.ok:
        raise SnapshotCorruptError(
            f"target snapshot failed verification: "
            f"manifest_hash_ok={v.manifest_hash_ok}, "
            f"mismatched={len(v.mismatched_files)}, "
            f"missing={len(v.missing_files)}, "
            f"audit_clean={v.audit_clean}"
        )

    # ── 2. Pre-restore snapshot of current state ─────────────────────
    pre_restore = snapshot(
        backup_root=backup_root,
        label=f"pre-restore-{_now_id_safe()}",
        data_dir=data_dir, config_dir=config_dir,
    )

    # ── 3. Stage ─────────────────────────────────────────────────────
    snap_path, manifest = _resolve_snapshot(
        snapshot_id, backup_root=backup_root,
    )
    staging_dir = data_dir.parent / f".restore-staging-{_now_id_safe()}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    shutil.copytree(snap_path / "data", staging_dir / "data")
    shutil.copytree(snap_path / "config", staging_dir / "config")

    # ── 4. Audit the staged atoms.db ─────────────────────────────────
    staged_atoms = staging_dir / "data" / "atoms.db"
    audit_dict, _, _, _ = _atoms_audit_snapshot(staged_atoms)
    if not audit_dict.get("ok", False):
        raise RestoreRefusedError(
            f"staged atoms.db failed financial audit; refusing restore. "
            f"Pre-restore snapshot of current live state: "
            f"{pre_restore.snapshot_id}. Staging dir preserved at: "
            f"{staging_dir} for forensics. "
            f"Violations: {audit_dict.get('violations', [])}"
        )

    # ── 5. Atomic-ish swap under PROTOCOL-ZERO ───────────────────────
    protocol_zero.arm("backup-restore-in-progress")
    try:
        # Move live to .replaced-* (don't delete; if rename of new fails
        # we can swap back).
        replaced_data = data_dir.parent / (
            data_dir.name + f".replaced-{_now_id_safe()}"
        )
        replaced_config = config_dir.parent / (
            config_dir.name + f".replaced-{_now_id_safe()}"
        )
        if data_dir.exists():
            data_dir.rename(replaced_data)
        if config_dir.exists():
            config_dir.rename(replaced_config)
        try:
            (staging_dir / "data").rename(data_dir)
            (staging_dir / "config").rename(config_dir)
        except Exception:
            # Restore live state if the new rename fails.
            if replaced_data.exists():
                replaced_data.rename(data_dir)
            if replaced_config.exists():
                replaced_config.rename(config_dir)
            raise

        # Clean up the now-empty staging shell and the .replaced-* dirs.
        # We delete .replaced-* only after successful rename of new dirs.
        if replaced_data.exists():
            shutil.rmtree(replaced_data, ignore_errors=True)
        if replaced_config.exists():
            shutil.rmtree(replaced_config, ignore_errors=True)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
    finally:
        # Always disarm; the operator can manually re-arm if needed.
        protocol_zero.disarm()

    # ── 6. Observability ─────────────────────────────────────────────
    try:
        from .events import emit_event
        emit_event(
            "backup-restore-d", plane="control",
            trace_id=f"backup-restore:{snapshot_id}",
            payload={
                "restored_snapshot_id": manifest.snapshot_id,
                "pre_restore_snapshot_id": pre_restore.snapshot_id,
                "atoms_count": manifest.atoms_count,
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[backup] restore event emit failed: {exc!r}", file=sys.stderr)

    return RestoreResult(
        snapshot_id=manifest.snapshot_id,
        pre_restore_snapshot_id=pre_restore.snapshot_id,
        restored_at=_now_iso(),
        staged_audit_clean=True,
    )


# ─── Status ─────────────────────────────────────────────────────────────────


def status(*, backup_root: Optional[Path] = None) -> BackupStatus:
    """Single-screen view. Tier 0."""
    backup_root = backup_root or default_backup_root()
    snaps = list_snapshots(backup_root=backup_root)
    if not snaps:
        return BackupStatus(
            backup_root=str(backup_root),
            snapshot_count=0, total_bytes=0,
            most_recent_snapshot_id=None, most_recent_age_seconds=None,
            oldest_snapshot_id=None, last_verify_ok=None,
        )

    total = sum(s.total_bytes for s in snaps)
    most_recent = snaps[0]
    oldest = snaps[-1]
    try:
        recent_dt = datetime.strptime(
            most_recent.created_at, "%Y-%m-%dT%H:%M:%S.%fZ",
        ).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - recent_dt).total_seconds()
    except ValueError:
        age = None

    # Quick verify of the most recent snapshot (without re-running audit
    # so it's cheap; hash-only).
    quick_v = verify(
        most_recent.snapshot_id, backup_root=backup_root, run_audit=False,
    )

    return BackupStatus(
        backup_root=str(backup_root),
        snapshot_count=len(snaps),
        total_bytes=total,
        most_recent_snapshot_id=most_recent.snapshot_id,
        most_recent_age_seconds=age,
        oldest_snapshot_id=oldest.snapshot_id,
        last_verify_ok=quick_v.ok,
    )


__all__ = [
    "BackupError",
    "BackupStatus",
    "FileEntry",
    "PruneResult",
    "RestoreRefusedError",
    "RestoreResult",
    "RetentionPolicy",
    "SnapshotCorruptError",
    "SnapshotManifest",
    "SnapshotNotFoundError",
    "VerifyResult",
    "default_backup_root",
    "list_snapshots",
    "prune",
    "restore",
    "snapshot",
    "status",
    "verify",
]
