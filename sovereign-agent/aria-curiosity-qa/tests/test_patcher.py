"""Patcher tests for aria-curiosity-qa — verify against the CURRENT live
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
PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "curiosity.py"


def test_applies_idempotent_compiles():
    import py_compile
    import tempfile

    once, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert MARK in once
    twice, changed2 = patch_app(once)
    assert changed2 is False and twice == once
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(once)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_wonder_verb_and_idle_timer_added():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert 'elif verb == "wonder":' in new
    assert "set_interval(1800.0, self._maybe_autonomous_wonder)" in new


def test_autonomous_wondering_is_hard_gated():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    idx = new.index("def _maybe_autonomous_wonder")
    body = new[idx:idx + 900]
    assert "autonomous_wonder_allowed" in body
    assert "_session_running" in body  # never while she's working
    assert "self._busy" in body


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_app("no anchors here")


def test_payload_compiles_and_carries_the_bounds():
    import py_compile

    py_compile.compile(str(PAYLOAD), doraise=True)
    text = PAYLOAD.read_text(encoding="utf-8")
    assert "MAX_AUTONOMOUS_PER_DAY" in text
    assert "SOV_NO_WONDER" in text
