"""Path-scope enforcement. Architecture §6 invariant 6, §7 matrix.

In BUSY mode, every write/edit/copy target must resolve (via realpath) to a
descendant of $AGENT_HOME/sandbox. Symlinks are followed before the check.

This is one of three layers; the others are:
  - tier matrix: tools above tier 1 are not in the available list when mode=BUSY
  - bwrap: $PROJECT_DIR is --ro-bind under BUSY, --bind otherwise
"""
from __future__ import annotations

from pathlib import Path

from .config import SETTINGS
from .modes import Mode


class PathScopeViolation(Exception):
    """Raised when a path-touching tool tries to write outside its allowed scope."""

    def __init__(self, path: str, *, mode: Mode, allowed: str):
        self.path = path
        self.mode = mode
        self.allowed = allowed
        super().__init__(
            f"path-scope violation: {path!r} not under {allowed!r} (mode={mode})"
        )


def _realpath(p: str | Path) -> Path:
    """Resolve symlinks, .., etc. Returns absolute Path."""
    # strict=False: target may not exist yet (write_file creates it)
    return Path(p).expanduser().resolve(strict=False)


def is_under(path: str | Path, root: str | Path) -> bool:
    """True iff realpath(path) is the root or a descendant of root."""
    rp = _realpath(path)
    rr = _realpath(root)
    try:
        rp.relative_to(rr)
        return True
    except ValueError:
        return False


# garden-d — her assigned garden: a per-session workspace granted
# EXPLICITLY by the operator in the /work line (scope `dir:`). Declared →
# ALL modes: writes must land under garden ∪ sandbox (in BUSY this extends
# beyond the sandbox — by the human's own written grant; elsewhere it ADDS
# a wall where none existed). Not declared → behavior byte-for-byte as
# before. Module state is process-scoped: one session runs per process.
_ACTIVE_GARDEN: Path | None = None


def set_garden(path: str | Path) -> Path:
    global _ACTIVE_GARDEN
    _ACTIVE_GARDEN = _realpath(path)
    return _ACTIVE_GARDEN


def clear_garden() -> None:
    global _ACTIVE_GARDEN
    _ACTIVE_GARDEN = None


def active_garden() -> Path | None:
    return _ACTIVE_GARDEN


def check_write_path(target: str | Path, mode: Mode) -> Path:
    """Validate a write/edit destination for the given mode.

    Returns the resolved Path on success.
    Raises PathScopeViolation if mode == BUSY and target is outside sandbox.

    Non-BUSY modes have no path guard here — they delegate to the bwrap mount
    layout and per-tool confirmation prompts (see §7 matrix).

    garden-d: when a garden is planted (set_garden), EVERY mode requires
    writes under garden ∪ sandbox — see the module note above.
    """
    resolved = _realpath(target)
    if _ACTIVE_GARDEN is not None:
        sandbox = SETTINGS.paths.sandbox_dir
        if not (is_under(resolved, _ACTIVE_GARDEN) or is_under(resolved, sandbox)):
            raise PathScopeViolation(
                str(resolved), mode=mode, allowed=f"{_ACTIVE_GARDEN} (garden) or {sandbox}"
            )
        return resolved
    if mode == Mode.BUSY:
        sandbox = SETTINGS.paths.sandbox_dir
        if not is_under(resolved, sandbox):
            raise PathScopeViolation(
                str(resolved), mode=mode, allowed=str(sandbox)
            )
    return resolved
