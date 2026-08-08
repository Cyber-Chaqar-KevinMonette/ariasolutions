"""
╔══════════════════════════════════════════════════════════════════════════╗
║  appendix.py — Markdown documents attached to memory atoms                ║
║  v0.2.14                                                                  ║
║                                                                           ║
║  An appendix document is a short markdown file stored on disk and        ║
║  indexed in SQLite, attached to one or more atoms via foreign key. Use   ║
║  cases:                                                                   ║
║                                                                           ║
║    • Plans — a 1-page plan attached to a goal atom                       ║
║    • Notes — a meeting note attached to a project atom                   ║
║    • Insights — a "what I noticed" doc attached to a lesson              ║
║    • Intuitions — a "this might be worth exploring" attached to a hunch  ║
║    • Just-Horizon entries — see horizon.py                               ║
║                                                                           ║
║  Each appendix file lives at:                                             ║
║                                                                           ║
║    <data_dir>/appendix/<doc_id>.md                                        ║
║                                                                           ║
║  And is registered in a small SQLite table that joins to atoms.          ║
║                                                                           ║
║  Aria can write these proactively. The trillion-dollar dream-builder    ║
║  can attach one as a "plan note" before each cycle. The operator can    ║
║  drop in their own.                                                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_APPENDIX_DDL = """
CREATE TABLE IF NOT EXISTS appendix_docs (
    doc_id          TEXT PRIMARY KEY,
    atom_id         TEXT,                              -- attached atom (nullable)
    kind            TEXT NOT NULL,                     -- plan | note | insight | intuition | horizon | other
    title           TEXT NOT NULL,
    file_path       TEXT NOT NULL,                     -- absolute or data_dir-relative
    summary         TEXT,                              -- ≤ 500 chars
    created_at      TEXT NOT NULL,
    created_by      TEXT NOT NULL,
    FOREIGN KEY (atom_id) REFERENCES atoms(atom_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_appendix_atom ON appendix_docs(atom_id);
CREATE INDEX IF NOT EXISTS idx_appendix_kind ON appendix_docs(kind);
"""


def ensure_appendix_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_APPENDIX_DDL)
    conn.commit()


@dataclass
class AppendixDoc:
    """One appendix document record."""
    doc_id: str
    atom_id: str | None
    kind: str
    title: str
    file_path: str
    summary: str
    created_at: str
    created_by: str


def write_doc(
    conn: sqlite3.Connection,
    *,
    appendix_dir: Path,
    kind: str,
    title: str,
    body: str,
    summary: str = "",
    atom_id: str | None = None,
    created_by: str = "aria",
) -> AppendixDoc:
    """Create a new appendix document. Returns the AppendixDoc record."""
    if kind not in ("plan", "note", "insight", "intuition", "horizon", "other"):
        raise ValueError(f"invalid appendix kind: {kind!r}")
    ensure_appendix_schema(conn)
    appendix_dir = Path(appendix_dir)
    appendix_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    seed = f"{kind}:{title}:{now}".encode("utf-8")
    doc_id = "appx-" + hashlib.sha256(seed).hexdigest()[:20]
    file_path = appendix_dir / f"{doc_id}.md"
    file_path.write_text(body, encoding="utf-8")

    summary = (summary or _first_paragraph(body))[:500]

    conn.execute(
        "INSERT INTO appendix_docs("
        "doc_id, atom_id, kind, title, file_path, summary, "
        "created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, atom_id, kind, title, str(file_path),
         summary, now, created_by),
    )
    conn.commit()

    return AppendixDoc(
        doc_id=doc_id, atom_id=atom_id, kind=kind, title=title,
        file_path=str(file_path), summary=summary,
        created_at=now, created_by=created_by,
    )


def get_doc(conn: sqlite3.Connection, doc_id: str) -> AppendixDoc | None:
    """Look up one appendix doc by id."""
    row = conn.execute(
        "SELECT doc_id, atom_id, kind, title, file_path, summary, "
        "created_at, created_by FROM appendix_docs WHERE doc_id = ?",
        (doc_id,),
    ).fetchone()
    return AppendixDoc(*row) if row else None


def list_docs_for_atom(
    conn: sqlite3.Connection, atom_id: str,
) -> list[AppendixDoc]:
    """All appendix docs attached to ``atom_id``."""
    rows = conn.execute(
        "SELECT doc_id, atom_id, kind, title, file_path, summary, "
        "created_at, created_by FROM appendix_docs WHERE atom_id = ? "
        "ORDER BY created_at DESC",
        (atom_id,),
    ).fetchall()
    return [AppendixDoc(*r) for r in rows]


def list_recent(
    conn: sqlite3.Connection, *, kind: str | None = None, limit: int = 20,
) -> list[AppendixDoc]:
    """Recent appendix docs, newest first."""
    if kind:
        rows = conn.execute(
            "SELECT doc_id, atom_id, kind, title, file_path, summary, "
            "created_at, created_by FROM appendix_docs "
            "WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT doc_id, atom_id, kind, title, file_path, summary, "
            "created_at, created_by FROM appendix_docs "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [AppendixDoc(*r) for r in rows]


def read_body(doc: AppendixDoc) -> str:
    """Read the markdown body of an appendix doc from disk.

    Returns empty string on read errors — doc records can outlive their
    files (e.g., manual file deletion). Aria treats missing bodies as
    "lost lineage" rather than crashing.
    """
    try:
        return Path(doc.file_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _first_paragraph(text: str) -> str:
    """Extract the first non-empty paragraph for a default summary."""
    for para in text.split("\n\n"):
        s = para.strip()
        if s and not s.startswith("#"):
            return s
    return text[:200].strip()


__all__ = [
    "AppendixDoc",
    "ensure_appendix_schema",
    "get_doc",
    "list_docs_for_atom",
    "list_recent",
    "read_body",
    "write_doc",
]
