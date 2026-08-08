"""staged_status.py — one shared answer to "is this staged aria-* module applied?"

2026-08-02: this exact detection logic (does every payload .py file byte-match its
live counterpart) had drifted into 3 independent copies — scripts/apply_queue.sh's
_is_applied(), cockpit/apply_screen.py's _is_applied(), and
cockpit/apply_queue_screen.py's _pending_modules() — each only checking
tests/test_<slug>.py, which is false for any module whose payload files are named
after what they DO, not the aria-<slug> folder (aria-real-estate ships
real_estate_gate.py, not test_real_estate.py). One shared implementation here;
callers that need it in bash (scripts/apply_queue.sh) keep their own copy since
this is a Python module, but every Python caller should import this, not
reimplement it.
"""
from __future__ import annotations

from pathlib import Path


def is_applied(repo_root: Path, module_name: str) -> bool:
    """True iff `module_name` (an "aria-<slug>" folder under repo_root) is applied.

    Checks, in order: tests/test_<slug>.py exists, a backups/ dir exists (legacy
    marker some older apply scripts write), or every payload .py file is byte-
    identical to its live src/sovereign_agent/ counterpart (the fallback that
    covers modules whose payload files aren't named after their own slug)."""
    repo_root = Path(repo_root)
    slug = module_name.removeprefix("aria-").replace("-", "_")
    if (repo_root / "tests" / f"test_{slug}.py").is_file():
        return True
    if (repo_root / module_name / "backups").is_dir():
        return True
    payload = repo_root / module_name / "payload" / "src" / "sovereign_agent"
    if not payload.is_dir():
        return False
    found = False
    for f in payload.rglob("*.py"):
        found = True
        rel = f.relative_to(payload)
        live = repo_root / "src" / "sovereign_agent" / rel
        if not live.is_file() or f.read_bytes() != live.read_bytes():
            return False
    return found


def pending_modules(repo_root: Path) -> list[str]:
    """Staged aria-*/ modules with an apply script that aren't applied yet."""
    repo_root = Path(repo_root)
    out: list[str] = []
    for script in sorted(repo_root.glob("aria-*/apply_*.sh")):
        name = script.parent.name
        if not is_applied(repo_root, name):
            out.append(name)
    return out
