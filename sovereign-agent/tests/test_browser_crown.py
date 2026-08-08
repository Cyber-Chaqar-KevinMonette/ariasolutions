"""test_browser_crown.py — Tests for M50 (Browser Crown)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── html_to_text / extract_links unit tests ───────────────────────────────────


def test_html_to_text_strips_tags():
    from sovereign_agent.browser import html_to_text
    html = "<html><body><p>Hello <b>world</b></p><script>alert(1)</script></body></html>"
    result = html_to_text(html)
    assert "Hello" in result
    assert "world" in result
    assert "alert" not in result


def test_html_to_text_strips_style():
    from sovereign_agent.browser import html_to_text
    html = "<html><head><style>body{color:red}</style></head><body><p>content</p></body></html>"
    result = html_to_text(html)
    assert "color" not in result
    assert "content" in result


def test_extract_links_resolves_relative():
    from sovereign_agent.browser import extract_links
    html = '<a href="/about">About</a><a href="https://other.com">Other</a>'
    links = extract_links(html, "https://example.com/page")
    hrefs = [lnk["href"] for lnk in links]
    assert "https://example.com/about" in hrefs
    assert "https://other.com" in hrefs


def test_extract_links_skips_anchors_and_js():
    from sovereign_agent.browser import extract_links
    html = '<a href="#top">Top</a><a href="javascript:void(0)">JS</a><a href="/page">Page</a>'
    links = extract_links(html, "https://example.com")
    hrefs = [lnk["href"] for lnk in links]
    assert "#top" not in " ".join(hrefs)
    assert "javascript" not in " ".join(hrefs)
    assert "https://example.com/page" in hrefs


# ── BrowserSession unit tests ─────────────────────────────────────────────────


def test_browser_session_initial_state():
    from sovereign_agent.browser import BrowserSession
    session = BrowserSession()
    assert session.current() is None
    assert session.history() == []


def test_browser_session_navigate_stores_page():
    from sovereign_agent.browser import BrowserSession
    session = BrowserSession()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>Test Page</title></head><body><p>Hello</p></body></html>"
    mock_response.url = "https://example.com/"
    mock_response.headers = {"content-type": "text/html"}
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    session._httpx_client = mock_client
    page = session.navigate("https://example.com/")
    assert page is not None
    assert page.status_code == 200
    assert "Hello" in page.text
    assert session.current() is page
    assert "https://example.com/" in session.history()


def test_browser_session_clear_resets_state():
    from sovereign_agent.browser import BrowserSession
    session = BrowserSession()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><p>hi</p></body></html>"
    mock_response.url = "https://example.com/"
    mock_response.headers = {"content-type": "text/html"}
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    session._httpx_client = mock_client
    session.navigate("https://example.com/")
    session.clear()
    assert session.current() is None
    assert session.history() == []


def test_playwright_available_check():
    from sovereign_agent.browser import BrowserSession
    result = BrowserSession.playwright_available()
    assert isinstance(result, bool)


# ── browser_status tool tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_status_no_page():
    from sovereign_agent.tools.browser_tools import BrowserStatusTool
    tool = BrowserStatusTool()
    mock_session = MagicMock()
    mock_session.current.return_value = None
    mock_session.history.return_value = []
    with (
        patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session),
        patch("asyncio.to_thread", new=AsyncMock(return_value=False)),
    ):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["has_page"] is False
    assert result.output["current_url"] is None


@pytest.mark.asyncio
async def test_browser_status_with_page():
    from sovereign_agent.tools.browser_tools import BrowserStatusTool
    tool = BrowserStatusTool()
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.title = "Example"
    mock_session.current.return_value = mock_page
    mock_session.history.return_value = ["https://example.com"]
    with (
        patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session),
        patch("asyncio.to_thread", new=AsyncMock(return_value=False)),
    ):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["has_page"] is True
    assert result.output["current_url"] == "https://example.com"
    assert result.output["history_depth"] == 1


# ── browser_navigate tool tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_navigate_success():
    from sovereign_agent.tools.browser_tools import BrowserNavigateTool
    from sovereign_agent.browser import PageResult
    tool = BrowserNavigateTool()
    fake_page = MagicMock(spec=PageResult)
    fake_page.status_code = 200
    fake_page.url = "https://example.com"
    fake_page.title = "Example Domain"
    fake_page.fetched_at = "2026-06-20T00:00:00Z"
    fake_page.text_length = 100
    fake_page.link_count = 5
    fake_page.as_dict.return_value = {
        "url": "https://example.com", "title": "Example Domain",
        "status_code": 200, "fetched_at": "2026-06-20T00:00:00Z",
        "text_length": 100, "link_count": 5,
    }
    fake_page.text = "This domain is for illustrative examples."
    mock_session = MagicMock()
    with (
        patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session),
        patch("asyncio.to_thread", new=AsyncMock(return_value=fake_page)),
    ):
        result = await tool.execute(
            tool.Args(url="https://example.com"),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_browser_navigate_http_error():
    from sovereign_agent.tools.browser_tools import BrowserNavigateTool
    from sovereign_agent.browser import PageResult
    tool = BrowserNavigateTool()
    fake_page = MagicMock(spec=PageResult)
    fake_page.status_code = 404
    fake_page.url = "https://example.com/notfound"
    mock_session = MagicMock()
    with (
        patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session),
        patch("asyncio.to_thread", new=AsyncMock(return_value=fake_page)),
    ):
        result = await tool.execute(
            tool.Args(url="https://example.com/notfound"),
            trace_id="t1",
        )
    assert not result.ok
    assert "404" in result.error


# ── browser_read tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_read_no_page():
    from sovereign_agent.tools.browser_tools import BrowserReadTool
    tool = BrowserReadTool()
    mock_session = MagicMock()
    mock_session.current.return_value = None
    with patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert not result.ok
    assert "No page loaded" in result.error


@pytest.mark.asyncio
async def test_browser_read_text_format():
    from sovereign_agent.tools.browser_tools import BrowserReadTool
    tool = BrowserReadTool()
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.title = "Example"
    mock_page.text = "Hello world this is the page content"
    mock_page.html_content = "<html><body>Hello world</body></html>"
    mock_page.fetched_at = "2026-06-20T00:00:00Z"
    mock_session.current.return_value = mock_page
    with patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session):
        result = await tool.execute(tool.Args(format="text"), trace_id="t1")
    assert result.ok
    assert "Hello world" in result.output["content"]
    assert result.output["format"] == "text"


# ── browser_links tool tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_links_no_page():
    from sovereign_agent.tools.browser_tools import BrowserLinksTool
    tool = BrowserLinksTool()
    mock_session = MagicMock()
    mock_session.current.return_value = None
    with patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert not result.ok


@pytest.mark.asyncio
async def test_browser_links_returns_list():
    from sovereign_agent.tools.browser_tools import BrowserLinksTool
    tool = BrowserLinksTool()
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.links = [
        {"href": "https://example.com/about", "text": "About"},
        {"href": "https://other.com", "text": "Other"},
    ]
    mock_session.current.return_value = mock_page
    with patch("sovereign_agent.tools.browser_tools.get_browser_session", return_value=mock_session):
        result = await tool.execute(tool.Args(limit=10), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 2


# ── Tool registration tests ───────────────────────────────────────────────────


def test_browser_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "browser_status" in _TIER_REGISTRY
    assert "browser_navigate" in _TIER_REGISTRY
    assert "browser_read" in _TIER_REGISTRY
    assert "browser_links" in _TIER_REGISTRY
    assert "browser_search" in _TIER_REGISTRY
    assert _TIER_REGISTRY["browser_status"].tier == 0
    assert _TIER_REGISTRY["browser_navigate"].tier == 2
    assert _TIER_REGISTRY["browser_read"].tier == 0
    assert _TIER_REGISTRY["browser_links"].tier == 0
    assert _TIER_REGISTRY["browser_search"].tier == 2


def test_browser_tools_have_failure_modes():
    from sovereign_agent.tools.browser_tools import (
        BrowserStatusTool, BrowserNavigateTool, BrowserReadTool,
        BrowserLinksTool, BrowserSearchTool,
    )
    for cls in (
        BrowserStatusTool, BrowserNavigateTool, BrowserReadTool,
        BrowserLinksTool, BrowserSearchTool,
    ):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── loop marker test ──────────────────────────────────────────────────────────


def test_loop_has_browser_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "browser-crown-d" in src, "browser-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
