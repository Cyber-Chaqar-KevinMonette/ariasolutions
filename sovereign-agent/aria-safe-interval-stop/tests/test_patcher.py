"""Text-transform tests for patcher.py — proves the loop.py/agent_session.py
patches apply cleanly against the CURRENT live files, are idempotent, and
fail loudly (never silently) if an anchor has moved."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher import MARK, PatchError, patch_agent_session, patch_loop  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOP_PY = REPO_ROOT / "src" / "sovereign_agent" / "loop.py"
AGENT_SESSION_PY = REPO_ROOT / "src" / "sovereign_agent" / "agent_session.py"


def _pre_apply_backup(name: str) -> str:
    """The genuine pre-apply snapshot (written by apply_safe_interval_stop.sh
    before patching) — the only reliable way to test "does patch_X raise on
    a broken anchor" now that live already has MARK and the patcher's own
    early-exit (`if MARK in text: return text, False`) would otherwise
    short-circuit before ever reaching the anchor search."""
    backups = sorted(Path(__file__).resolve().parents[1].glob("backups/*/" + name))
    assert backups, f"no pre-apply backup found for {name!r}"
    return backups[0].read_text(encoding="utf-8")


def test_patch_loop_applies_and_is_idempotent():
    text = LOOP_PY.read_text(encoding="utf-8")
    once, _ = patch_loop(text)  # changed may be False if already applied
    assert MARK in once
    assert "effective_wall_limit(budget)" in once
    twice, changed_again = patch_loop(once)
    assert not changed_again
    assert twice == once


def test_patch_agent_session_applies_and_is_idempotent():
    text = AGENT_SESSION_PY.read_text(encoding="utf-8")
    once, _ = patch_agent_session(text)  # changed may be False if already applied
    assert MARK in once
    assert "effective_wall_limit(budget)" in once
    twice, changed_again = patch_agent_session(once)
    assert not changed_again
    assert twice == once


def test_patch_loop_raises_loud_on_moved_anchor():
    pre_apply = _pre_apply_backup("loop.py.bak")
    broken = pre_apply.replace(
        "from .modes import BudgetExceeded, Mode, RunBudget\n",
        "from .modes import BudgetExceeded, Mode, RunBudget as RB\n",
    )
    with pytest.raises(PatchError):
        patch_loop(broken)


def test_patch_agent_session_raises_loud_on_moved_anchor():
    pre_apply = _pre_apply_backup("agent_session.py.bak")
    broken = pre_apply.replace(
        "from .modes import BudgetExceeded, Mode, RunBudget\n",
        "from .modes import BudgetExceeded, Mode, RunBudget as RB\n",
    )
    with pytest.raises(PatchError):
        patch_agent_session(broken)


def test_patched_loop_compiles():
    import py_compile
    import tempfile

    text = LOOP_PY.read_text(encoding="utf-8")
    patched, _ = patch_loop(text)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(patched)
        tmp_name = fh.name
    py_compile.compile(tmp_name, doraise=True)


def test_patched_agent_session_compiles():
    import py_compile
    import tempfile

    text = AGENT_SESSION_PY.read_text(encoding="utf-8")
    patched, _ = patch_agent_session(text)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(patched)
        tmp_name = fh.name
    py_compile.compile(tmp_name, doraise=True)
