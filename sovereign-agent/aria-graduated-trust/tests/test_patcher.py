"""Pre-apply structural checks for aria-graduated-trust's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import ALL_PATCHES, DOC_PATCHES, DOCTRINE_WORDS, MARK, PatchError  # noqa: E402

SRC = REPO_ROOT / "src/sovereign_agent"


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        tmp = fh.name
    try:
        py_compile.compile(tmp, doraise=True)
        return True
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_every_code_patch_applies_compiles_and_is_idempotent():
    for rel, fn in ALL_PATCHES.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_every_doc_patch_applies_and_is_idempotent():
    files = {
        "handoff/02_SAFETY_MODEL.md": REPO_ROOT / "handoff/02_SAFETY_MODEL.md",
        "CLAUDE.md": REPO_ROOT / "CLAUDE.md",
    }
    for rel, fn in DOC_PATCHES.items():
        text = files[rel].read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert DOCTRINE_WORDS in new, rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_agent_session_patch_carries_the_new_api():
    new, _ = ALL_PATCHES["agent_session.py"](
        (SRC / "agent_session.py").read_text(encoding="utf-8"))
    for name in ("hold_and_continue", "held_subtask_ids", "PlanRevision",
                 "approve_all_held", "revise_pending_subtasks",
                 "awaiting_approval"):
        assert name in new, name


def test_runner_patch_bumps_to_v3_and_adds_trust_wing():
    new, _ = ALL_PATCHES["proving_ground/runner.py"](
        (SRC / "proving_ground/runner.py").read_text(encoding="utf-8"))
    assert 'SUITE_VERSION = "v3"' in new
    assert "OFFLINE_TASKS.update(TRUST_TASKS)" in new


def test_cli_patch_adds_the_session_subcommands():
    new, _ = ALL_PATCHES["cli.py"](
        (SRC / "cli.py").read_text(encoding="utf-8"))
    for name in ("session_status_cmd", "session_approve_cmd",
                 "session_skip_cmd", "session_revise_cmd"):
        assert f"def {name}" in new, name
    assert 'app.add_typer(session_app, name="session")' in new


def test_app_patch_adds_the_approve_verb():
    new, _ = ALL_PATCHES["cockpit/app.py"](
        (SRC / "cockpit/app.py").read_text(encoding="utf-8"))
    assert 'verb == "approve"' in new
    assert "_approve_held_subtask" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
    for rel, fn in DOC_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
