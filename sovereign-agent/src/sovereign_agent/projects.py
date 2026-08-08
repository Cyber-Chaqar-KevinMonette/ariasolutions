"""
╔══════════════════════════════════════════════════════════════════════════╗
║  projects.py — Named project tracking with snapshot + diff                ║
║  v0.2.12                                                                  ║
║                                                                           ║
║  A "project" is a named directory the operator wants the agent to know    ║
║  about across sessions. Scanning a project produces a snapshot — file     ║
║  paths + sizes + content hashes — saved alongside the metadata.           ║
║                                                                           ║
║  When the operator says "I updated <project>", `sov projects update`      ║
║  re-scans, diffs against the last snapshot, and:                          ║
║    1. Reports added/modified/removed files                                ║
║    2. Optionally atomizes the diff so the dream-runner / palace can see   ║
║       what changed                                                        ║
║    3. Replaces the snapshot                                               ║
║                                                                           ║
║  This is the bridge between "the operator does work outside the agent"    ║
║  and "the agent's memory of the operator's world."                        ║
║                                                                           ║
║  Storage layout:                                                          ║
║    <data_dir>/projects/<project_name>.yaml                                ║
║                                                                           ║
║  Snapshot is plain YAML: human-inspectable, hand-editable. Same atomic-   ║
║  write discipline as continuations and proposals.                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Default excludes — patterns matched against the *full* path. Same shape as
# the inventory planner's --exclude flag, so what you see in one is what you
# get in the other. Operators with exotic build setups override via --exclude.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "*/.git/*",
    "*/.venv/*",
    "*/venv/*",
    "*/node_modules/*",
    "*/__pycache__/*",
    "*/.pytest_cache/*",
    "*/.mypy_cache/*",
    "*/.ruff_cache/*",
    "*/dist/*",
    "*/build/*",
    "*/.tox/*",
    "*/.cache/*",
    "*/target/*",                   # rust
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.o",
    "*.class",
)


# ─── Errors ─────────────────────────────────────────────────────────────────


class ProjectError(Exception):
    """Base for project store errors."""


class ProjectNotFound(ProjectError):
    pass


class ProjectExists(ProjectError):
    pass


class ProjectCorrupt(ProjectError):
    """Malformed project YAML."""


# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass
class FileEntry:
    """One file's identity in a snapshot.

    ``hash`` is sha256 over the file contents, computed in 1 MiB chunks so
    a multi-GB tree won't blow memory. ``size`` and ``mtime`` are kept
    alongside to enable a fast "did this change at all?" check before
    re-hashing — the slow path of re-hashing everything happens only when
    the operator explicitly asks for a deep verify.
    """

    path: str            # path RELATIVE to the project root (POSIX-style)
    size: int
    mtime: float         # unix epoch seconds, fractional
    hash: str            # sha256 hex; "" if unhashed (rare; deep-scan fills it)


@dataclass
class ProjectSnapshot:
    """The persisted record for one named project.

    A snapshot is durable — atomic-replaced on update, never appended to.
    The diff is computed in memory between two snapshots; the old one is
    overwritten only after the diff is reported back to the operator.
    """

    name: str                              # operator-chosen, unique per data dir
    root: str                              # absolute path
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    excludes: list[str] = field(default_factory=list)
    files: list[FileEntry] = field(default_factory=list)
    notes: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    def file_index(self) -> dict[str, FileEntry]:
        """Map relative-path → FileEntry. O(N) build, used for diffing."""
        return {f.path: f for f in self.files}


@dataclass
class ProjectDiff:
    """Result of comparing two snapshots of the same project.

    Reported when ``sov projects update`` runs. Each entry is a relative
    path; the operator can grep / process the lists from `--json` output.
    """

    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged_count: int = 0

    @property
    def changed_count(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)

    @property
    def is_empty(self) -> bool:
        return self.changed_count == 0

    def summary(self) -> str:
        return (
            f"{len(self.added)} added, {len(self.modified)} modified, "
            f"{len(self.removed)} removed "
            f"({self.unchanged_count} unchanged)"
        )


# ─── Scanner ────────────────────────────────────────────────────────────────


def _hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """sha256 of the file's bytes, streamed to bound memory.

    Returns empty string on read error — the caller decides whether to
    skip or surface that. We never re-raise IO errors from the scanner;
    the operator gets a count of skipped-unreadable files instead, which
    is friendlier than a one-bad-file aborting the entire scan.
    """
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _path_matches_any(path_str: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path_str, pat) for pat in patterns)


def scan_directory(
    root: Path,
    *,
    excludes: list[str] | None = None,
    follow_symlinks: bool = False,
    max_files: int = 0,
) -> list[FileEntry]:
    """Walk ``root`` and produce a sorted list of FileEntry.

    Sort order is stable (relative-path lexicographic) so two snapshots of
    an unchanged tree compare equal. ``max_files=0`` is unbounded; >0 caps
    after that many files.

    Excludes: full-path glob patterns. Defaults to DEFAULT_EXCLUDES; pass
    [] to override and start from a clean slate. The operator's --exclude
    flags are *appended* to the defaults, not replacement, in the typical
    invocation — that's the inventory planner's behavior and we match it.
    """
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ProjectError(f"scan_directory: not a directory: {root}")

    if excludes is None:
        excludes = list(DEFAULT_EXCLUDES)

    out: list[FileEntry] = []
    # os.walk gives us follow_symlinks control + per-directory pruning,
    # which matters for large trees with .git or node_modules. We prune
    # whole directories early when their full path matches an exclude.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Prune subdirs in place — modifying dirnames is the documented
        # idiom for telling os.walk to skip a subtree.
        dirnames[:] = [
            d for d in dirnames
            if not _path_matches_any(os.path.join(dirpath, d), excludes)
        ]

        for name in filenames:
            full = Path(dirpath) / name
            full_str = str(full)
            if _path_matches_any(full_str, excludes):
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            if not _is_regular_file(full, follow_symlinks):
                continue
            try:
                rel = full.resolve().relative_to(root).as_posix()
            except ValueError:
                # Rare: a symlink resolves outside the root. Skip.
                continue
            out.append(FileEntry(
                path=rel,
                size=st.st_size,
                mtime=st.st_mtime,
                hash=_hash_file(full),
            ))
            if max_files > 0 and len(out) >= max_files:
                break
        if max_files > 0 and len(out) >= max_files:
            break

    out.sort(key=lambda f: f.path)
    return out


def _is_regular_file(path: Path, follow_symlinks: bool) -> bool:
    """True if ``path`` is a regular file (or, optionally, a symlink to one).

    We don't snapshot devices / pipes / sockets even when they're stat-able.
    """
    try:
        if not follow_symlinks and path.is_symlink():
            return False
        return path.is_file()
    except OSError:
        return False


def diff_snapshots(old: ProjectSnapshot, new: ProjectSnapshot) -> ProjectDiff:
    """Compute the symmetric difference between two snapshots.

    ``modified`` entries are determined by hash inequality first (always
    reliable) then by size+mtime as a fallback when one side has empty
    hash (rare; deep-scan errors). This means a touched-but-unchanged
    file is *not* flagged as modified — the hash is the source of truth.
    """
    old_idx = old.file_index()
    new_idx = new.file_index()
    old_paths = set(old_idx.keys())
    new_paths = set(new_idx.keys())

    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    modified: list[str] = []
    unchanged = 0
    for p in sorted(new_paths & old_paths):
        a, b = old_idx[p], new_idx[p]
        if a.hash and b.hash:
            if a.hash != b.hash:
                modified.append(p)
            else:
                unchanged += 1
        else:
            # Fall back to size+mtime. Less reliable but better than
            # silently ignoring a difference.
            if a.size != b.size or abs(a.mtime - b.mtime) > 0.5:
                modified.append(p)
            else:
                unchanged += 1
    return ProjectDiff(
        added=added, modified=modified, removed=removed,
        unchanged_count=unchanged,
    )


# ─── Atomization (diff → atoms.db) ──────────────────────────────────────────


def atomize_diff(
    project_name: str,
    diff: ProjectDiff,
    new_snapshot: ProjectSnapshot,
    *,
    tag: str = "project_update",
) -> int:
    """Write one atom per changed file to atoms.db.

    Returns the number of atoms written. Idempotent: each atom has a
    deterministic id derived from project + path + new-hash, so re-running
    on the same diff is a no-op. The dream-runner inspects these atoms
    when it next ideates so its plans reflect operator changes.

    The atom shape mirrors ``summaries_to_atoms`` for consistency:
      - type='fact'
      - summary: short human sentence ("project foo: modified src/x.py")
      - content_ref: project name, change kind, full relative path
      - confidence: 0.95 (filesystem evidence is high-confidence)
      - created_by: actor='project_update'
    """
    from .db import open_atoms_db  # local import keeps projects.py importable
    # without sqlite-vec available — useful for tests of the pure-Python parts.

    if diff.is_empty:
        return 0

    new_idx = new_snapshot.file_index()
    items: list[tuple[str, str]] = []
    for p in diff.added:
        items.append(("added", p))
    for p in diff.modified:
        items.append(("modified", p))
    for p in diff.removed:
        items.append(("removed", p))

    written = 0
    conn = open_atoms_db()
    try:
        for kind, rel_path in items:
            file_hash = ""
            if kind != "removed" and rel_path in new_idx:
                file_hash = new_idx[rel_path].hash
            seed = f"{project_name}:{kind}:{rel_path}:{file_hash}".encode("utf-8")
            atom_id = "atom-projupd-" + hashlib.sha256(seed).hexdigest()[:20]

            existing = conn.execute(
                "SELECT atom_id FROM atoms WHERE atom_id = ?", (atom_id,)
            ).fetchone()
            if existing:
                continue

            summary = f"project {project_name}: {kind} {rel_path}"
            conn.execute(
                "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, "
                "parents, confidence, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    atom_id,
                    "fact",
                    summary[:990],
                    json.dumps({
                        "kind": "project_update",
                        "project": project_name,
                        "change": kind,
                        "rel_path": rel_path,
                        "hash": file_hash,
                        "tag": tag,
                    }),
                    json.dumps([]),
                    json.dumps([]),
                    0.95,
                    _utc_now(),
                    json.dumps({
                        "actor": "project_update",
                        "project": project_name,
                        "change": kind,
                    }),
                ),
            )
            written += 1
        conn.commit()
    finally:
        conn.close()
    return written


# ─── Store ──────────────────────────────────────────────────────────────────


class ProjectStore:
    """Filesystem-backed project snapshot registry.

    No locks — projects are operator-driven (one terminal at a time). If
    two operators race, last-write-wins is fine for this use case; the
    losing snapshot's diff just gets recomputed on the next update. We
    do use atomic-replace to avoid leaving a half-written YAML under a
    crashed pipe.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        if not _is_safe_name(name):
            raise ProjectError(
                f"invalid project name: {name!r} "
                f"(use letters, digits, -, _, .; no slashes or spaces)"
            )
        return self.root / f"{name}.yaml"

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def list_names(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.yaml") if p.is_file())

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def get(self, name: str) -> ProjectSnapshot:
        path = self._path(name)
        if not path.exists():
            raise ProjectNotFound(name)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ProjectCorrupt(f"YAML parse error in {path}: {e}") from e
        if not isinstance(data, dict):
            raise ProjectCorrupt(f"project {name}: root must be a mapping")
        return _from_yaml(data)

    def save(self, snap: ProjectSnapshot) -> None:
        self.ensure_root()
        path = self._path(snap.name)
        snap.updated_at = _utc_now()
        _atomic_write_text(path, yaml.safe_dump(_to_yaml(snap), sort_keys=False))

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.exists():
            return False
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return True


def _is_safe_name(name: str) -> bool:
    """Project names must be filename-safe — no path separators."""
    if not name:
        return False
    return all(c.isalnum() or c in "-_." for c in name)


def _to_yaml(snap: ProjectSnapshot) -> dict:
    return {
        "name": snap.name,
        "root": snap.root,
        "created_at": snap.created_at,
        "updated_at": snap.updated_at,
        "excludes": list(snap.excludes),
        "notes": snap.notes,
        "files": [asdict(f) for f in snap.files],
    }


def _from_yaml(d: dict) -> ProjectSnapshot:
    try:
        name = str(d["name"])
        root = str(d["root"])
    except KeyError as e:
        raise ProjectCorrupt(f"missing required field: {e.args[0]}") from None
    raw_files = d.get("files") or []
    if not isinstance(raw_files, list):
        raise ProjectCorrupt("'files' must be a list")
    files = [
        FileEntry(
            path=str(rf.get("path", "")),
            size=int(rf.get("size", 0)),
            mtime=float(rf.get("mtime", 0.0)),
            hash=str(rf.get("hash", "")),
        )
        for rf in raw_files if isinstance(rf, dict)
    ]
    return ProjectSnapshot(
        name=name,
        root=root,
        created_at=str(d.get("created_at") or _utc_now()),
        updated_at=str(d.get("updated_at") or _utc_now()),
        excludes=list(d.get("excludes") or []),
        files=files,
        notes=str(d.get("notes") or ""),
    )


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomic file write — same shape as continuation._atomic_write_text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


__all__ = [
    "DEFAULT_EXCLUDES",
    "FileEntry",
    "ProjectCorrupt",
    "ProjectDiff",
    "ProjectError",
    "ProjectExists",
    "ProjectNotFound",
    "ProjectSnapshot",
    "ProjectStore",
    "atomize_diff",
    "diff_snapshots",
    "scan_directory",
]
