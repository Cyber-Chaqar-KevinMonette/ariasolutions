"""mapper.py — the Canon-Embodiment organ: which mos_canon.py clauses are actually
lived in code, and which are declared but never cited anywhere else.

`mos_canon.py` already ships `ALL_CLAUSES` (35 `CanonClause` objects with stable
`.id` fields) and `CLAUSE_INDEX`/`get_clause()` — this organ doesn't re-parse the
canon file; it imports those directly and asks one honest question: does anything
OUTSIDE mos_canon.py itself cite this clause id?

A citation is a real signal a clause is lived, not just declared — e.g.
`training.py` calling `mc.get_clause("mos-priority-stack")`, or a tool's guidance
text naming `mos-signal-check`. A clause with zero citations outside its own
declaration is doctrine that isn't (yet, traceably) lived.

Ground truth as of 2026-07-03: **9 of 35** clauses are cited outside mos_canon.py.
This is a real, honest number — not the 30/35 an earlier, unverified planning pass
assumed. Most clauses are likely embodied in *spirit* (the behavior they describe
happens) without literally citing their id string; this organ measures the
narrower, stricter, and more useful signal: traceable citation, not vibes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_CANON_FILE_NAME = "mos_canon.py"

# cockpit-hardening-d (2026-07-20): this scan is re-run every 5s by
# _refresh_status_worker's gather_health() call, off the main thread. It
# had NO directory exclusion at all -- measured directly against this repo,
# that meant walking 1,440 .py files (src/ + every aria-*/ folder,
# INCLUDING every apply script's backups/ snapshot, which only ever grows).
# Diagnosed live via py-spy on a hung cockpit: this was the actual cause,
# not the /work session it looked like it was stuck on. Matches
# stewardship/glyph_sentinel.py's own EXCLUDE_DIRS convention, plus
# "backups" -- today's specific, newly-discovered growth vector.
EXCLUDE_DIRS = frozenset({
    ".venv", "venv", "__pycache__", "Archive", "dist", "build",
    ".git", "node_modules", "history", "backups",
})


@dataclass
class Location:
    path: str
    line: int
    excerpt: str


@dataclass
class CanonEmbodimentReport:
    embodied: dict[str, list[Location]] = field(default_factory=dict)
    orphaned: list[str] = field(default_factory=list)
    total_clauses: int = 0

    @property
    def embodied_count(self) -> int:
        return len(self.embodied)

    def summary(self) -> str:
        return (f"{self.embodied_count}/{self.total_clauses} clauses cited outside "
                f"{_CANON_FILE_NAME} · {len(self.orphaned)} orphaned")

    def as_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "embodied": {
                cid: [{"path": l.path, "line": l.line, "excerpt": l.excerpt} for l in locs]
                for cid, locs in self.embodied.items()
            },
            "orphaned": self.orphaned,
        }


def extract_clause_ids() -> list[str]:
    """Every clause id currently declared in mos_canon.py's ALL_CLAUSES."""
    from sovereign_agent.mos_canon import ALL_CLAUSES

    return [c.id for c in ALL_CLAUSES]


def find_references(
    repo_root: Path,
    clause_ids: list[str] | None = None,
    *,
    search_dirs: tuple[str, ...] = ("src", "aria-*"),
) -> CanonEmbodimentReport:
    """Search `search_dirs` for every clause id, excluding mos_canon.py itself
    (a clause always "references" its own declaration — that's not embodiment,
    it's the declaration). Returns which clauses have ≥1 outside citation and
    which have none."""
    if clause_ids is None:
        clause_ids = extract_clause_ids()

    files: list[Path] = []
    for pattern in search_dirs:
        for base in repo_root.glob(pattern):
            if not base.is_dir():
                continue
            files.extend(
                f for f in base.rglob("*.py")
                if not any(part in EXCLUDE_DIRS for part in f.parts)  # cockpit-hardening-d
                and not f.name.endswith(_CANON_FILE_NAME)  # path-scan: allow
                and ".bak" not in f.name  # path-scan: allow
            )

    embodied: dict[str, list[Location]] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(repo_root))
        for i, line in enumerate(text.splitlines(), start=1):
            for cid in clause_ids:
                if cid in line:
                    embodied.setdefault(cid, []).append(
                        Location(path=rel, line=i, excerpt=line.strip()[:160])
                    )

    orphaned = [cid for cid in clause_ids if cid not in embodied]
    return CanonEmbodimentReport(
        embodied=embodied, orphaned=orphaned, total_clauses=len(clause_ids),
    )
