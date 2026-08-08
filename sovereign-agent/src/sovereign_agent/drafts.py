"""
╔══════════════════════════════════════════════════════════════════════════╗
║  drafts.py — final-draft archival for completed projects                 ║
║  v0.2.15.3 · Aria-Sovereign-V1                                            ║
║                                                                            ║
║  When a project reaches "done" — a directive completes, a planner emits  ║
║  a final artifact set, a release is cut — we want a single zipped,       ║
║  metadata-tagged record stored somewhere predictable so a human (or      ║
║  Aria) can review it later without spelunking through scratch dirs.      ║
║                                                                            ║
║  Layout:                                                                  ║
║    <data_dir>/drafts/                                                    ║
║      ├── 20260511-143205-trillion-dollar-plan.zip                        ║
║      ├── 20260511-143205-trillion-dollar-plan.json   ← sidecar           ║
║      └── ...                                                              ║
║                                                                            ║
║  The sidecar carries: title, label, source path, created_at, byte count, ║
║  file count, sha256 of the zip, who ran it (uid + hostname), and any     ║
║  free-form notes the caller passes in. This makes drafts greppable and   ║
║  diffable across time.                                                   ║
║                                                                            ║
║  Authority tier: 1 (reversible writes, bounded scope). Drafts live       ║
║  under data_dir and are listable/deletable via `sov drafts`.             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class DraftRecord:
    """One archived draft, on disk."""
    id: str                         # 20260511-143205-trillion-dollar-plan
    title: str                      # human-readable
    label: str = ""                 # short tag, optional
    zip_path: Path = field(default_factory=Path)
    sidecar_path: Path = field(default_factory=Path)
    source_path: str = ""
    created_at: str = ""            # ISO 8601 UTC
    bytes_total: int = 0
    file_count: int = 0
    sha256: str = ""
    host: str = ""
    user: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "label": self.label,
            "zip_path": str(self.zip_path),
            "sidecar_path": str(self.sidecar_path),
            "source_path": self.source_path,
            "created_at": self.created_at,
            "bytes_total": self.bytes_total,
            "file_count": self.file_count,
            "sha256": self.sha256,
            "host": self.host,
            "user": self.user,
            "notes": self.notes,
        }


# ── Path resolution ─────────────────────────────────────────────────────────


def _drafts_dir() -> Path:
    """Resolve <data_dir>/drafts, creating it if missing."""
    try:
        from .config import SETTINGS
        base = SETTINGS.paths.data_dir
    except Exception:  # noqa: BLE001
        # Fallback for tooling/tests that import this module in isolation.
        base = Path(os.environ.get("AGENT_DATA",
                                    Path.home() / ".local/share/sovereign-agent"))
    d = base / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slugify(s: str) -> str:
    """Filesystem-safe slug: lowercase, hyphenated, [a-z0-9-] only."""
    out = []
    for ch in s.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " _-./":
            out.append("-")
        # Else: drop silently. We're being permissive on input, strict on output.
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:64] or "untitled"


# ── The API ─────────────────────────────────────────────────────────────────


def archive_project(
    title: str,
    source_path: Path | str,
    *,
    label: str = "",
    notes: str = "",
    exclude_patterns: Optional[Iterable[str]] = None,
) -> DraftRecord:
    """Archive a directory (or single file) into <data_dir>/drafts/<id>.zip.

    Args:
        title: Human title — used in the filename and sidecar.
        source_path: Directory or file to archive. Must exist.
        label: Optional short tag (e.g., "v0.2.15.3", "client-demo").
        notes: Free-form text stored in the sidecar.
        exclude_patterns: Glob patterns (matched against the relative
            posix path inside the zip) to skip.

    Returns:
        A DraftRecord describing where it landed and what's inside.

    Raises:
        FileNotFoundError: source_path doesn't exist.
        OSError: zip creation failed (no space, perms, etc.).
    """
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"source_path does not exist: {source}")

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S")
    slug = _slugify(title)
    draft_id = f"{ts}-{slug}"

    drafts = _drafts_dir()
    zip_path = drafts / f"{draft_id}.zip"
    sidecar_path = drafts / f"{draft_id}.json"

    excludes = list(exclude_patterns or [])

    def _is_excluded(rel: str) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(rel, pat) for pat in excludes)

    # Build the zip — DEFLATED for portability and reasonable compression.
    file_count = 0
    bytes_total = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if source.is_file():
            rel = source.name
            if not _is_excluded(rel):
                z.write(source, arcname=rel)
                file_count = 1
                bytes_total = source.stat().st_size
        else:
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(source).as_posix()
                if _is_excluded(rel):
                    continue
                z.write(path, arcname=rel)
                file_count += 1
                bytes_total += path.stat().st_size

    # Compute sha256 of the resulting zip — gives a stable identifier
    # for downstream tooling that wants to verify it hasn't been altered.
    sha = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)

    rec = DraftRecord(
        id=draft_id,
        title=title,
        label=label,
        zip_path=zip_path,
        sidecar_path=sidecar_path,
        source_path=str(source),
        created_at=now.isoformat(timespec="seconds"),
        bytes_total=bytes_total,
        file_count=file_count,
        sha256=sha.hexdigest(),
        host=socket.gethostname(),
        user=os.environ.get("USER", "unknown"),
        notes=notes,
    )

    # Write the sidecar last — if anything above failed, no half-written
    # sidecar gets left behind to confuse `list_drafts`.
    sidecar_path.write_text(
        json.dumps(rec.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return rec


def list_drafts() -> list[DraftRecord]:
    """Return all drafts in reverse chronological order (newest first).

    Each entry is reconstructed from its sidecar JSON. Drafts whose
    sidecar is missing or corrupt are skipped silently — they're either
    in-flight or already failed, and we don't want one bad file to break
    the listing.
    """
    drafts = _drafts_dir()
    out: list[DraftRecord] = []
    for sidecar in sorted(drafts.glob("*.json"), reverse=True):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        try:
            rec = DraftRecord(
                id=data["id"],
                title=data.get("title", ""),
                label=data.get("label", ""),
                zip_path=Path(data.get("zip_path", "")),
                sidecar_path=sidecar,
                source_path=data.get("source_path", ""),
                created_at=data.get("created_at", ""),
                bytes_total=int(data.get("bytes_total", 0)),
                file_count=int(data.get("file_count", 0)),
                sha256=data.get("sha256", ""),
                host=data.get("host", ""),
                user=data.get("user", ""),
                notes=data.get("notes", ""),
            )
        except (KeyError, ValueError):
            continue
        out.append(rec)
    return out


def show_draft(draft_id: str) -> Optional[DraftRecord]:
    """Look up one draft by id. Returns None if not found."""
    for d in list_drafts():
        if d.id == draft_id:
            return d
    return None
