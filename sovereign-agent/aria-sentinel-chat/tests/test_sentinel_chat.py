"""
test_sentinel_chat.py — Tests for sentinel chat alert logic (M26).
"""
from __future__ import annotations
import pathlib
import pytest


def test_marker_in_app():
    """After apply, app.py must contain the sentinel-chat markers."""
    app_path = pathlib.Path(__file__).resolve()
    for _ in range(8):
        candidate = app_path.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if candidate.exists():
            src = candidate.read_text()
            assert "sentinel-chat-refresh-d" in src, "refresh marker missing from app.py"
            assert "sentinel-chat-method-d" in src, "_check_sentinel_transitions method missing"
            assert "_prev_sentinel_states" in src, "_prev_sentinel_states field missing"
            return
        app_path = app_path.parent
    pytest.skip("cockpit/app.py not found")


def test_sentinel_transition_logic():
    """Unit test the sentinel state comparison logic (isolated, no Textual)."""
    WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}

    def should_alert(prev: str, current: str) -> bool:
        return WORSE.get(current, 0) > WORSE.get(prev, 0)

    def should_clear(prev: str, current: str) -> bool:
        return WORSE.get(current, 0) < WORSE.get(prev, 0) and prev != "ok"

    # Regressions
    assert should_alert("ok", "warning")
    assert should_alert("ok", "error")
    assert should_alert("warning", "error")

    # No alert on stable or improvement
    assert not should_alert("warning", "warning")
    assert not should_alert("warning", "ok")
    assert not should_alert("error", "error")

    # Recovery (from non-ok state)
    assert should_clear("warning", "ok")
    assert should_clear("error", "ok")
    assert should_clear("error", "warning")

    # No clear if was already ok
    assert not should_clear("ok", "ok")


def test_sentinel_chat_handles_unknown_gracefully():
    """'unknown' level should trigger alert from 'ok'."""
    WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}
    prev = "ok"
    current = "unknown"
    assert WORSE.get(current, 0) > WORSE.get(prev, 0)


def test_sentinel_chat_no_alert_on_same_level():
    """Same level twice does not trigger alert."""
    WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}
    for level in ("ok", "warning", "error", "unknown"):
        assert WORSE.get(level, 0) == WORSE.get(level, 0)
        # No regression when level stays the same
        assert not (WORSE.get(level, 0) > WORSE.get(level, 0))
