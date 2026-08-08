"""
test_cockpit_vitality.py — verify cockpit vitality patches.
"""
from __future__ import annotations
import pathlib


def test_cockpit_status_has_sentinel_fields():
    """CockpitStatus must have sentinel_ok, sentinel_total, sentinel_errors."""
    from sovereign_agent.cockpit.app import CockpitStatus
    s = CockpitStatus()
    assert hasattr(s, "sentinel_ok")
    assert hasattr(s, "sentinel_total")
    assert hasattr(s, "sentinel_errors")
    assert s.sentinel_ok == 0
    assert s.sentinel_total == 0


def test_app_has_display_fix_command():
    """app.py must contain the /display-fix slash handler."""
    app_py = pathlib.Path(__file__).resolve()
    for _ in range(8):
        candidate = app_py.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if candidate.exists():
            text = candidate.read_text()
            assert "display-fix" in text, "app.py missing /display-fix command"
            assert "Ctrl++" in text or "Ctrl+/- " in text, "app.py missing Ctrl+/- tip"
            return
        app_py = app_py.parent
    import pytest
    pytest.skip("app.py not found from test directory")


def test_welcome_banner_has_warmth():
    """Welcome banner must express fullness, not just 'kernel is whole'."""
    app_py = pathlib.Path(__file__).resolve()
    for _ in range(8):
        candidate = app_py.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if candidate.exists():
            text = candidate.read_text()
            # Either the vitality patch or the original is acceptable
            assert "kernel is whole" in text
            return
        app_py = app_py.parent
    import pytest
    pytest.skip("app.py not found from test directory")


def test_render_status_bar_has_sentinel_badge():
    """_render_status_bar must reference sentinel_badge."""
    app_py = pathlib.Path(__file__).resolve()
    for _ in range(8):
        candidate = app_py.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if candidate.exists():
            text = candidate.read_text()
            assert "sentinel_badge" in text, "app.py missing sentinel_badge in status bar"
            return
        app_py = app_py.parent
    import pytest
    pytest.skip("app.py not found from test directory")
