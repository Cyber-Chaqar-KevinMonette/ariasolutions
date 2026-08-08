"""Patcher tests for aria-one-thread — verify against the CURRENT live
app.py, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app  # noqa: E402

REPO_ROOT = STAGING.parent
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"
PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "thread_identity.py"


def _live() -> str:
    return APP_PY.read_text(encoding="utf-8")


def test_applies_idempotent_compiles():
    import py_compile
    import tempfile

    once, _ = patch_app(_live())
    assert MARK in once
    twice, changed2 = patch_app(once)
    assert changed2 is False and twice == once
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(once)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_session_id_becomes_persisted_thread_id_with_uuid_fallback():
    new, _ = patch_app(_live())
    assert "from sovereign_agent.thread_identity import thread_id" in new
    # the fallback survives
    assert 'f"cockpit-{_uuid_ccd.uuid4().hex[:12]}"' in new


def test_wake_restore_is_best_effort_and_escaped():
    new, _ = patch_app(_live())
    assert "restore_tail as _ot_tail" in new
    assert "──── earlier, from our thread ────" in new
    idx = new.index("_ot_tail(n_turns=30)")
    surrounding = new[max(0, idx - 600):idx + 800]
    assert "try:" in surrounding and "except Exception" in surrounding
    assert "_ot_escape" in surrounding  # arbitrary content never breaks Rich markup


def test_transcript_gains_the_join_key():
    new, _ = patch_app(_live())
    assert '{ts}·{self._chunk_session_id}' in new


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_app("no anchors here")


def test_payload_compiles():
    import py_compile

    py_compile.compile(str(PAYLOAD), doraise=True)
