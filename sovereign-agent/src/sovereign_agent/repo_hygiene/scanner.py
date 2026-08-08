"""repo_hygiene/scanner.py — stray root-level script detection.

Non-recursive by design: ``Path.glob("*.py")`` only returns direct
children of the repo root, so every legitimate location (src/, tests/,
scripts/, aria-<name>/ staged modules, archive/, .venv/, ...) is
naturally excluded without maintaining an explicit allowlist — real code
never lives loose at the root in this repo, only scratch work does.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class StrayScript:
    """One Python file sitting directly at the repo root — exactly the
    shape of the 38 one-off patch scripts that sat unnoticed for three
    days. ``symbol`` is the DispositionLedger's key (the bare filename,
    unique at root by construction)."""
    symbol: str
    path: str
    size_bytes: int
    modified_at: str

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
        }


@dataclass
class RepoScan:
    scripts: list[StrayScript]

    def summary(self) -> str:
        n = len(self.scripts)
        return "no stray root-level scripts" if n == 0 else f"{n} stray root-level script(s)"


def scan_repo_root(repo_root: Path) -> RepoScan:
    """Walk exactly the repo root, one level, for loose *.py files."""
    scripts: list[StrayScript] = []
    for py in sorted(Path(repo_root).glob("*.py")):
        if not py.is_file():
            continue
        stat = py.stat()
        scripts.append(StrayScript(
            symbol=py.name,
            path=str(py),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        ))
    return RepoScan(scripts=scripts)


__all__ = ["StrayScript", "RepoScan", "scan_repo_root"]
