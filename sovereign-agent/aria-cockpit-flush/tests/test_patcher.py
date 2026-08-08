"""Patcher tests for aria-cockpit-flush — verify the patch function against
the CURRENT live app.py, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app  # noqa: E402

REPO_ROOT = STAGING.parent
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"


def _live() -> str:
    return APP_PY.read_text(encoding="utf-8")


def test_applies_and_compiles():
    import py_compile
    import tempfile

    new, _ = patch_app(_live())
    assert MARK in new
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_idempotent():
    once, _ = patch_app(_live())
    twice, changed2 = patch_app(once)
    assert changed2 is False and twice == once


def test_on_unmount_seals_chunks_and_fsyncs_events():
    new, _ = patch_app(_live())
    idx = new.index("def on_unmount(self) -> None:")
    body = new[idx:idx + 900]
    assert "seal_now()" in body
    assert "force_fsync()" in body
    # Best-effort discipline: both wrapped
    assert body.count("except Exception") >= 2


def test_no_preexisting_on_unmount_shadowed():
    """CockpitApp must not already define on_unmount — the patch would
    silently shadow it."""
    assert _live().count("def on_unmount") == 0
    new, _ = patch_app(_live())
    assert new.count("def on_unmount") == 1


def test_error_handler_surfaces_ollama_reason():
    new, _ = patch_app(_live())
    idx = new.index("hint = \"\"")
    body = new[idx:idx + 800]
    assert "probe_ollama" in body
    assert "probe.healthy" in body
    assert "reason_phrase()" in body
    # And the original generic message is preserved as the fallback shape
    assert 'conversation error: {exc!r}{hint}' in new


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_app("no anchors here")
