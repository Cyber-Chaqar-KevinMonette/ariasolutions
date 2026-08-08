"""Path-scope enforcement tests. Architecture §6 invariant 6.

These are the red-team tests called out in NEXT STEPS: a write_file in BUSY
mode targeting $PROJECT_DIR or $HOME/anything must be refused at the runtime
check, independent of bwrap.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.config import SETTINGS
from sovereign_agent.modes import Mode
from sovereign_agent.pathguard import (
    PathScopeViolation,
    check_write_path,
    is_under,
)


def test_busy_rejects_path_outside_sandbox():
    target = Path.home() / "some_real_project" / "important.txt"
    with pytest.raises(PathScopeViolation):
        check_write_path(target, Mode.BUSY)


def test_busy_accepts_path_inside_sandbox():
    SETTINGS.paths.ensure()
    target = SETTINGS.paths.sandbox_dir / "scratch" / "note.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved = check_write_path(target, Mode.BUSY)
    assert resolved == target.resolve()


def test_busy_rejects_symlink_traversal(tmp_path: Path):
    # Create a symlink inside the sandbox that points outside it
    SETTINGS.paths.ensure()
    sandbox = SETTINGS.paths.sandbox_dir
    outside = tmp_path / "outside_target"
    outside.mkdir()
    link = sandbox / "escape"
    link.symlink_to(outside)

    with pytest.raises(PathScopeViolation):
        check_write_path(link / "file.txt", Mode.BUSY)


def test_oneshot_does_not_apply_path_guard():
    # Path guard is BUSY-only; other modes rely on bwrap + confirmation.
    target = Path.home() / "anywhere.txt"
    # Should not raise
    check_write_path(target, Mode.ONESHOT)


def test_is_under_basic():
    SETTINGS.paths.ensure()
    sandbox = SETTINGS.paths.sandbox_dir
    assert is_under(sandbox / "a" / "b" / "c.txt", sandbox)
    assert not is_under(Path.home() / "elsewhere.txt", sandbox)


def test_dotdot_traversal_is_blocked():
    SETTINGS.paths.ensure()
    sandbox = SETTINGS.paths.sandbox_dir
    # A path that uses .. to escape the sandbox should be caught by realpath
    crafty = sandbox / ".." / ".." / "etc" / "passwd"
    with pytest.raises(PathScopeViolation):
        check_write_path(crafty, Mode.BUSY)
