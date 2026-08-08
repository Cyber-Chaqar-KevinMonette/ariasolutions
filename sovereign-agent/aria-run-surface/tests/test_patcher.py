"""Patcher tests for aria-run-surface — verify the patch function against
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
PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "cockpit" / "run_surface.py"


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


def test_failure_flags_render_red():
    new, _ = patch_app(_live())
    assert 'flag.endswith("-x")' in new
    # the red branch must come BEFORE the generic "end" match
    assert new.index('flag.endswith("-x")') < new.index('elif "end" in flag:')


def test_run_strip_added_and_refreshed():
    new, _ = patch_app(_live())
    assert 'id="run-strip"' in new
    assert "def _refresh_run_strip" in new
    assert "self._refresh_run_strip()  # run-surface-d" in new


def test_rich_render_falls_through_for_unknown_flags():
    """The routing must only intercept KNOWN families — the generic
    renderer stays reachable (rich is None → fall through)."""
    new, _ = patch_app(_live())
    idx = new.index("_rich = _run_surface.render_rich_event(ev)")
    tail = new[idx:idx + 300]
    assert "if _rich is not None:" in tail


def test_status_bar_gains_mode_and_breaker():
    new, _ = patch_app(_live())
    assert "load_mode as _rs_load_mode" in new
    assert "_RUN_STATE.breaker_open_tool" in new


def test_tool_start_and_token_usage_handlers_survive():
    """The pre-existing special handlers must remain reachable (their
    flags return None from the rich renderer by design)."""
    new, _ = patch_app(_live())
    assert 'if flag == "tool-start-d":' in new
    assert 'if flag == "token-usage-d":' in new


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_app("no anchors here")


def test_payload_compiles():
    import py_compile

    py_compile.compile(str(PAYLOAD), doraise=True)
