"""test_qol.py — Tests for Quality-of-Life enhancements."""
from __future__ import annotations

import pathlib


# ── loop.py marker tests ──────────────────────────────────────────────────────


def _loop_src() -> str:
    root = pathlib.Path(__file__).resolve()
    for _ in range(10):
        candidate = root.parent / "src" / "sovereign_agent" / "loop.py"
        if candidate.exists():
            return candidate.read_text()
        root = root.parent
    return ""


def test_loop_has_qol_boot_marker():
    src = _loop_src()
    if not src:
        import pytest; pytest.skip("loop.py not found")
    assert "qol-boot-d" in src
    assert "session_brief_read()" in src
    assert "eval_score()" in src


def test_loop_has_qol_session_end_marker():
    src = _loop_src()
    if not src:
        import pytest; pytest.skip("loop.py not found")
    assert "qol-session-end-d" in src
    assert "session_brief_write" in src


def test_loop_has_auto_notify_marker():
    src = _loop_src()
    if not src:
        import pytest; pytest.skip("loop.py not found")
    assert "qol-auto-notify-d" in src
    assert "gdbus" in src


# ── cockpit app.py marker tests ───────────────────────────────────────────────


def _app_src() -> str:
    root = pathlib.Path(__file__).resolve()
    for _ in range(10):
        candidate = root.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if candidate.exists():
            return candidate.read_text()
        root = root.parent
    return ""


def test_cockpit_has_voice_binding():
    src = _app_src()
    if not src:
        import pytest; pytest.skip("app.py not found")
    assert "qol-voice-binding-d" in src
    assert "ctrl+p" in src
    assert "voice_push_to_talk" in src


def test_cockpit_has_voice_state():
    src = _app_src()
    if not src:
        import pytest; pytest.skip("app.py not found")
    assert "qol-voice-state-d" in src
    assert "_voice_recording" in src


def test_cockpit_has_tool_map_additions():
    src = _app_src()
    if not src:
        import pytest; pytest.skip("app.py not found")
    assert "qol-tool-map-d" in src
    assert '"eval_score"' in src
    assert '"browser_navigate"' in src
    assert '"notify"' in src


def test_cockpit_has_new_slash_commands():
    src = _app_src()
    if not src:
        import pytest; pytest.skip("app.py not found")
    assert "qol-slash-d" in src
    assert 'verb == "eval"' in src
    assert 'verb == "score"' in src
    assert 'verb == "browse"' in src
    assert 'verb == "voice"' in src


def test_cockpit_has_voice_action():
    src = _app_src()
    if not src:
        import pytest; pytest.skip("app.py not found")
    assert "qol-voice-action-d" in src
    assert "action_voice_push_to_talk" in src
    assert "get_voice_recorder" in src
    assert "WhisperTranscriber" in src


# ── playwright is now available ───────────────────────────────────────────────


def test_playwright_importable():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        assert True
    except ImportError:
        import pytest; pytest.skip("playwright not installed")


def test_browser_session_playwright_available():
    from sovereign_agent.browser import BrowserSession
    result = BrowserSession.playwright_available()
    assert result is True, "playwright should be installed and importable"


def test_browser_navigate_has_js_render_arg():
    from sovereign_agent.tools.browser_tools import BrowserNavigateTool
    import inspect
    sig = inspect.signature(BrowserNavigateTool.Args.__init__ if hasattr(BrowserNavigateTool.Args, '__init__') else BrowserNavigateTool.Args)
    # Check via pydantic model fields
    fields = BrowserNavigateTool.Args.model_fields
    assert "js_render" in fields, "BrowserNavigateTool.Args should have js_render field"


# ── html_to_text void element fix ────────────────────────────────────────────


def test_html_to_text_handles_void_elements():
    from sovereign_agent.browser import html_to_text
    # link and meta are void elements — should not corrupt skip counter
    html = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="utf-8"><link rel="stylesheet" href="style.css">'
        '<title>Test</title></head>'
        '<body><h1>Hello</h1><p>World</p></body></html>'
    )
    result = html_to_text(html)
    assert "Hello" in result
    assert "World" in result


def test_html_to_text_playwright_real_html():
    from sovereign_agent.browser import html_to_text
    # Simulate the kind of HTML playwright returns
    html = (
        '<!DOCTYPE html><html lang="en"><head><title>Example</title>'
        '<link rel="icon" href="data:,"><meta name="viewport" content="width=device-width">'
        '<style>body{color:red}</style></head>'
        '<body><div><h1>Example Domain</h1>'
        '<p>This domain is for docs.</p></div></body></html>'
    )
    result = html_to_text(html)
    assert "Example Domain" in result
    assert "This domain is for docs" in result
    assert "color" not in result  # style stripped


# ── pyproject.toml browser extra ─────────────────────────────────────────────


def test_pyproject_has_browser_extra():
    root = pathlib.Path(__file__).resolve()
    for _ in range(10):
        p = root.parent / "pyproject.toml"
        if p.exists():
            content = p.read_text()
            assert "browser" in content
            assert "playwright" in content
            return
        root = root.parent
    import pytest; pytest.skip("pyproject.toml not found")
