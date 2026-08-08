"""test_cockpit_god.py — Tests for M46 (God-Tier Cockpit Upgrade)."""
from __future__ import annotations

import json
import pytest


# ── _TOOL_BUTTON_MAP tests ────────────────────────────────────────────────────


def test_tool_button_map_exists():
    from sovereign_agent.cockpit.app import _TOOL_BUTTON_MAP
    assert isinstance(_TOOL_BUTTON_MAP, dict)
    assert len(_TOOL_BUTTON_MAP) >= 8, "Expected ≥ 8 entries in _TOOL_BUTTON_MAP"


def test_tool_button_map_has_known_tools():
    from sovereign_agent.cockpit.app import _TOOL_BUTTON_MAP
    expected = {"aria_status", "vessel_comfort", "get_emotions", "list_objectives"}
    for tool in expected:
        assert tool in _TOOL_BUTTON_MAP, f"{tool} should be in _TOOL_BUTTON_MAP"


def test_tool_button_map_values_are_valid_keys():
    from sovereign_agent.cockpit.app import _TOOL_BUTTON_MAP, PALETTE_COMMANDS
    valid_keys = {pc.key for pc in PALETTE_COMMANDS}
    for tool_name, button_key in _TOOL_BUTTON_MAP.items():
        assert button_key in valid_keys, (
            f"_TOOL_BUTTON_MAP[{tool_name!r}] = {button_key!r} "
            f"is not a valid palette key. Valid: {sorted(valid_keys)}"
        )


# ── Slash command tests ───────────────────────────────────────────────────────


def test_slash_emotion_is_handled():
    """Check that /emotion verb is recognized in _handle_slash."""
    import inspect
    from sovereign_agent.cockpit import app as cockpit_app
    src = inspect.getsource(cockpit_app)
    assert '"emotion"' in src or "verb == \"emotion\"" in src, \
        "/emotion slash command not found in cockpit app.py"


def test_slash_vision_is_handled():
    import inspect
    from sovereign_agent.cockpit import app as cockpit_app
    src = inspect.getsource(cockpit_app)
    assert '"vision"' in src or 'verb == "vision"' in src, \
        "/vision slash command not found in cockpit app.py"


def test_slash_brief_is_handled():
    import inspect
    from sovereign_agent.cockpit import app as cockpit_app
    src = inspect.getsource(cockpit_app)
    assert '"brief"' in src or 'verb == "brief"' in src, \
        "/brief slash command not found in cockpit app.py"


def test_slash_auto_is_handled():
    import inspect
    from sovereign_agent.cockpit import app as cockpit_app
    src = inspect.getsource(cockpit_app)
    assert '"auto"' in src or 'verb == "auto"' in src, \
        "/auto slash command not found in cockpit app.py"


# ── CSS tests ─────────────────────────────────────────────────────────────────


def test_aria_active_css_exists():
    from sovereign_agent.cockpit.app import CockpitApp
    css = CockpitApp.CSS
    assert "aria-active" in css, "aria-active CSS class missing from CockpitApp.CSS"


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_cockpit_has_god_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if c.exists():
            src = c.read_text()
            assert "cockpit-god-d" in src, "cockpit-god-d missing from cockpit/app.py"
            return
        p = p.parent
    pytest.skip("cockpit/app.py not found")
