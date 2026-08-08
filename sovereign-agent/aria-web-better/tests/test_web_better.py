"""
test_web_better.py — Tests for web_extract and web_research tools (M22).
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "web_extract" in _TIER_REGISTRY
    assert _TIER_REGISTRY["web_extract"].tier == 0
    assert "web_research" in _TIER_REGISTRY
    assert _TIER_REGISTRY["web_research"].tier == 0


def test_failure_modes():
    from sovereign_agent.tools.web_better import WebExtractTool, WebResearchTool
    assert WebExtractTool.failure_modes
    assert WebResearchTool.failure_modes


def test_allowlist_contains_expected_domains():
    from sovereign_agent.tools.web_better import _DEFAULT_ALLOWLIST
    assert "stackoverflow.com" in _DEFAULT_ALLOWLIST
    assert "docs.python.org" in _DEFAULT_ALLOWLIST
    assert "arxiv.org" in _DEFAULT_ALLOWLIST
    assert "developer.mozilla.org" in _DEFAULT_ALLOWLIST
    assert "github.com" in _DEFAULT_ALLOWLIST


def test_check_url_blocks_unknown_domain():
    from sovereign_agent.tools.web_better import _check_url
    ok, err = _check_url("https://evil.example.com/steal")
    assert not ok
    assert "allowlist" in err


def test_check_url_allows_known_domain():
    from sovereign_agent.tools.web_better import _check_url
    ok, host = _check_url("https://docs.python.org/3/library/os.html")
    assert ok
    assert "docs.python.org" in host


def test_check_url_allows_subdomain():
    from sovereign_agent.tools.web_better import _check_url
    # e.g. foo.readthedocs.io should match readthedocs.io
    ok, _ = _check_url("https://foo.readthedocs.io/en/latest/")
    assert ok


def test_check_url_blocks_non_https():
    from sovereign_agent.tools.web_better import _check_url
    ok, err = _check_url("ftp://docs.python.org/file.tar.gz")
    assert not ok


def test_html_to_text_strips_tags():
    from sovereign_agent.tools.web_better import _html_to_text
    html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
    text = _html_to_text(html)
    assert "Hello" in text
    assert "World" in text
    assert "<h1>" not in text
    assert "<p>" not in text


def test_html_to_text_handles_entities():
    from sovereign_agent.tools.web_better import _html_to_text
    html = "<p>A &amp; B &lt;3 C</p>"
    text = _html_to_text(html)
    assert "&amp;" not in text
    assert "A & B" in text or "A" in text


def test_html_to_text_caps_at_max_chars():
    from sovereign_agent.tools.web_better import _html_to_text
    html = "<p>" + "x" * 10000 + "</p>"
    text = _html_to_text(html, max_chars=100)
    assert len(text) <= 100


@pytest.mark.asyncio
async def test_web_extract_blocks_unknown_domain():
    from sovereign_agent.tools.web_better import WebExtractTool
    tool = WebExtractTool()
    result = await tool.execute(
        tool.Args(url="https://evil.example.com/data"),
        trace_id="t1",
    )
    assert not result.ok
    assert "allowlist" in result.error


@pytest.mark.asyncio
async def test_web_extract_success():
    """web_extract fetches and strips HTML cleanly."""
    from sovereign_agent.tools.web_better import WebExtractTool
    import httpx

    fake_html = "<html><body><h1>Test Page</h1><p>Clean content here.</p></body></html>"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.content = fake_html.encode()
    mock_response.url = "https://docs.python.org/3/test.html"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("sovereign_agent.tools.web_better.httpx.AsyncClient", return_value=mock_client):
        tool = WebExtractTool()
        result = await tool.execute(
            tool.Args(url="https://docs.python.org/3/test.html"),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "Test Page" in result.output
    assert "Clean content here" in result.output
    assert "<h1>" not in result.output


@pytest.mark.asyncio
async def test_web_extract_non_2xx():
    from sovereign_agent.tools.web_better import WebExtractTool
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {}
    mock_response.content = b""
    mock_response.url = "https://docs.python.org/missing"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("sovereign_agent.tools.web_better.httpx.AsyncClient", return_value=mock_client):
        tool = WebExtractTool()
        result = await tool.execute(
            tool.Args(url="https://docs.python.org/missing"),
            trace_id="t1",
        )

    assert not result.ok
    assert "404" in result.error


@pytest.mark.asyncio
async def test_web_research_synthesizes_results():
    """web_research returns synthesized block with sources."""
    from sovereign_agent.tools.web_better import WebResearchTool
    from sovereign_agent.tools.base import ToolResult

    # Mock web_search result
    search_result = ToolResult(
        ok=True,
        output=[
            {"url": "https://docs.python.org/3/library/asyncio.html",
             "title": "asyncio docs", "snippet": "Async library"},
            {"url": "https://stackoverflow.com/q/12345",
             "title": "Stack Overflow", "snippet": "Python async answer"},
        ],
        metadata={"query": "python asyncio", "result_count": 2},
    )

    extract_result = ToolResult(
        ok=True,
        output="Clean extracted content about asyncio.",
        metadata={"url": "https://docs.python.org/3/library/asyncio.html", "chars": 40},
    )

    with patch(
        "sovereign_agent.tools.web_better.WebExtractTool.execute",
        AsyncMock(return_value=extract_result),
    ):
        from sovereign_agent.tools.web_search import WebSearchTool
        with patch.object(
            WebSearchTool, "execute",
            AsyncMock(return_value=search_result),
        ):
            tool = WebResearchTool()
            result = await tool.execute(
                tool.Args(query="python asyncio", depth=2),
                trace_id="t1",
            )

    assert result.ok, result.error
    assert "Research:" in result.output
    assert "Sources:" in result.output
    assert result.metadata["sources_fetched"] >= 1
