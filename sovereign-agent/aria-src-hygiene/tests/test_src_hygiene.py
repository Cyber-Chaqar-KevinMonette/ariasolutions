"""Guard: the source tree must stay free of stray *.bak backup files.

Backup files in src/ clutter search, can confuse tooling, bloat the installed
package, and (in one case) placed a mos_canon.py.bak next to a sealed file.
Real backups belong in staging backups/ dirs, never in src/.
"""
from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


def test_src_has_no_bak_files():
    root = _repo_root()
    stray = sorted(str(p.relative_to(root)) for p in (root / "src").rglob("*.bak*") if p.is_file())
    assert not stray, (
        f"{len(stray)} stray .bak file(s) found under src/ — move them to a staging "
        f"quarantine, not the source tree:\n  " + "\n  ".join(stray[:20])
    )


def test_no_sealed_file_backup_in_src():
    # A sealed/charter backup must never appear in the tree.
    root = _repo_root()
    bad = [
        str(p.relative_to(root))
        for p in (root / "src").rglob("*.bak*")
        if p.is_file() and any(s in p.name.lower() for s in ("signal", "charter"))
    ]
    assert not bad, f"sealed/charter-file backup present in src/: {bad}"
