"""tools/browser_tools.py — Stateful Web Browser Tools (M50).

  browser_status()                          T0 — session state + playwright availability
  browser_navigate(url)                     T2 — fetch URL, update session state
  browser_read(format='text')               T0 — read current page (text or raw html)
  browser_links(limit=20)                   T0 — extract links from current page
  browser_search(query, engine='ddg')       T2 — web search + return result URLs
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level imports for testability
try:
    from sovereign_agent.browser import (
        BrowserSession,
        get_browser_session,
        html_to_text,
        extract_links,
    )
except ImportError:
    BrowserSession = None  # type: ignore[assignment]
    get_browser_session = None  # type: ignore[assignment]
    html_to_text = None  # type: ignore[assignment]
    extract_links = None  # type: ignore[assignment]

_SEARCH_URLS = {
    "ddg": "https://html.duckduckgo.com/html/?q={query}",
    "google": "https://www.google.com/search?q={query}",
}


# ── browser_status ────────────────────────────────────────────────────────────


class _StatusArgs(BaseModel):
    pass


class BrowserStatusTool(Tool[_StatusArgs]):
    name = "browser_status"
    tier = 0
    description = (
        "Show current browser session state: current URL, history depth, "
        "playwright availability (for JS rendering). "
        "Primary backend: httpx (stateful cookies, static HTML). "
        "Optional: install playwright for JS-rendered page support."
    )
    failure_modes = ("browser_unavailable",)
    Args = _StatusArgs

    async def execute(self, args: _StatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            session = get_browser_session()
            current = session.current()
            playwright_ok = await asyncio.to_thread(BrowserSession.playwright_available)
            return ToolResult(ok=True, output={
                "has_page": current is not None,
                "current_url": current.url if current else None,
                "current_title": current.title if current else None,
                "history_depth": len(session.history()),
                "playwright_available": playwright_ok,
                "backend": "httpx (static HTML) + playwright (JS)" if playwright_ok else "httpx (static HTML only)",
                "note": (
                    "Install playwright for JS support: pip install playwright && playwright install chromium"
                    if not playwright_ok else
                    "Full browser capabilities available."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"browser_status failed: {e}")


# ── browser_navigate ──────────────────────────────────────────────────────────


class _NavigateArgs(BaseModel):
    url: str = Field(description="Full URL to navigate to (https:// required for external sites).")
    js_render: bool = Field(
        default=False,
        description=(
            "Use playwright Chromium for JS rendering. "
            "Slower (~3-5s) but handles SPAs, React/Vue apps, and dynamic content. "
            "Falls back to httpx if playwright not installed."
        ),
    )
    timeout_s: int = Field(default=15, ge=1, le=60)


class BrowserNavigateTool(Tool[_NavigateArgs]):
    name = "browser_navigate"
    tier = 2
    description = (
        "Navigate to a URL and load the page into the browser session. "
        "Cookies and session state persist across calls. "
        "Set js_render=True for JavaScript-heavy sites (React, Vue, SPAs). "
        "After navigating, use browser_read() to get content and browser_links() to explore. "
        "T2: operator-confirmed because external HTTP requests are visible network actions."
    )
    failure_modes = ("network_error", "timeout", "invalid_url", "http_error")
    Args = _NavigateArgs

    async def execute(self, args: _NavigateArgs, *, trace_id: str) -> ToolResult:
        try:
            session = get_browser_session()
            page = await asyncio.to_thread(session.navigate, args.url, args.js_render)
            if page.status_code >= 400:
                return ToolResult(
                    ok=False,
                    error=f"HTTP {page.status_code} fetching {args.url}",
                )
            return ToolResult(ok=True, output={
                **page.as_dict(),
                "text_preview": page.text[:500],
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"browser_navigate failed: {e}")


# ── browser_read ──────────────────────────────────────────────────────────────


class _ReadArgs(BaseModel):
    format: Literal["text", "html"] = Field(
        default="text",
        description="'text' for human-readable (default), 'html' for raw markup.",
    )
    max_chars: int = Field(default=8000, ge=100, le=50_000)


class BrowserReadTool(Tool[_ReadArgs]):
    name = "browser_read"
    tier = 0
    description = (
        "Read the content of the current page (loaded by browser_navigate). "
        "Returns extracted text by default — scripts, styles, and nav boilerplate stripped. "
        "Use format='html' for the raw markup."
    )
    failure_modes = ("no_page_loaded",)
    Args = _ReadArgs

    async def execute(self, args: _ReadArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            session = get_browser_session()
            current = session.current()
            if current is None:
                return ToolResult(
                    ok=False,
                    error="No page loaded. Call browser_navigate(url) first.",
                )
            if args.format == "html":
                content = current.html_content[: args.max_chars]
            else:
                content = current.text[: args.max_chars]
            return ToolResult(ok=True, output={
                "url": current.url,
                "title": current.title,
                "format": args.format,
                "content": content,
                "content_length": len(content),
                "fetched_at": current.fetched_at,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"browser_read failed: {e}")


# ── browser_links ─────────────────────────────────────────────────────────────


class _LinksArgs(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    same_domain_only: bool = Field(
        default=False,
        description="If True, return only links to the same domain as current page.",
    )


class BrowserLinksTool(Tool[_LinksArgs]):
    name = "browser_links"
    tier = 0
    description = (
        "Extract links from the current page. Returns href + link text. "
        "Use same_domain_only=True to stay on-site when crawling documentation. "
        "Requires a loaded page (call browser_navigate first)."
    )
    failure_modes = ("no_page_loaded",)
    Args = _LinksArgs

    async def execute(self, args: _LinksArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            session = get_browser_session()
            current = session.current()
            if current is None:
                return ToolResult(
                    ok=False,
                    error="No page loaded. Call browser_navigate(url) first.",
                )
            links = current.links
            if args.same_domain_only:
                from urllib.parse import urlparse  # noqa: PLC0415
                base_domain = urlparse(current.url).netloc
                links = [lnk for lnk in links if urlparse(lnk["href"]).netloc == base_domain]
            links = links[: args.limit]
            return ToolResult(ok=True, output={
                "url": current.url,
                "links": links,
                "count": len(links),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"browser_links failed: {e}")


# ── browser_search ────────────────────────────────────────────────────────────


class _SearchArgs(BaseModel):
    query: str = Field(max_length=500, description="Search query.")
    engine: Literal["ddg", "google"] = Field(
        default="ddg",
        description="Search engine: ddg (DuckDuckGo HTML, no JS needed) or google.",
    )
    limit: int = Field(default=10, ge=1, le=30)


class BrowserSearchTool(Tool[_SearchArgs]):
    name = "browser_search"
    tier = 2
    description = (
        "Web search via DuckDuckGo (or Google) and return result links. "
        "Uses browser_navigate internally — results go into session state. "
        "DDG HTML mode works without JS. "
        "T2 because this makes external network requests."
    )
    failure_modes = ("network_error", "timeout", "parse_failed")
    Args = _SearchArgs

    async def execute(self, args: _SearchArgs, *, trace_id: str) -> ToolResult:
        try:
            from urllib.parse import quote_plus  # noqa: PLC0415
            url = _SEARCH_URLS[args.engine].format(query=quote_plus(args.query))
            session = get_browser_session()
            page = await asyncio.to_thread(session.navigate, url)
            if page.status_code >= 400:
                return ToolResult(ok=False, error=f"Search HTTP {page.status_code}")
            links = [
                lnk for lnk in page.links
                if lnk["href"].startswith("http")
                and args.engine not in lnk["href"]
                and "duckduckgo" not in lnk["href"]
                and "google.com/search" not in lnk["href"]
            ][: args.limit]
            return ToolResult(ok=True, output={
                "query": args.query,
                "engine": args.engine,
                "results": links,
                "count": len(links),
                "text_preview": page.text[:1000],
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"browser_search failed: {e}")


__all__ = [
    "BrowserStatusTool",
    "BrowserNavigateTool",
    "BrowserReadTool",
    "BrowserLinksTool",
    "BrowserSearchTool",
]
