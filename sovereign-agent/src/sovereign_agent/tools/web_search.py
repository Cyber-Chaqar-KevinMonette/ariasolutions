"""web_search — Tier 0. Search the web for URLs to fetch.

Pairs with ``web_fetch``: ``web_search`` finds URLs, ``web_fetch`` retrieves
their content. Together they let the agent answer questions that require
internet access while keeping the agent fundamentally local-first.

**Optional feature.** This tool gracefully degrades when offline:

  - If ``AGENT_INTERNET=off`` (env var), the tool returns an error result
    explaining internet access is disabled. The agent loop treats this as
    a tool failure, not a crash.
  - If the network call fails (DNS error, timeout, no route), the tool
    returns a clean error. The agent can choose what to do — usually
    falling back to memory_search or asking for help.
  - If ``AGENT_INTERNET`` is not set, defaults to ``on`` IFF a quick
    connectivity probe succeeds at tool-instantiation time.

Backend: DuckDuckGo HTML endpoint (no API key, no telemetry, no tracking).
We scrape the result list and return the top N URLs + titles. The agent
typically follows up with ``web_fetch`` on a chosen URL.

The agent's awareness of this tool is through the standard tool-schema
mechanism; the loop only includes web_search in the tool list when both:
  (a) AGENT_INTERNET ≠ off, and
  (b) connectivity probe succeeded at startup.

This way an agent on an offline machine doesn't even know to try, instead
of trying and failing repeatedly.
"""
from __future__ import annotations

import os
import re
import socket
from urllib.parse import unquote

import httpx
from pydantic import BaseModel, Field

from .base import Tool, ToolResult


_INTERNET_ENABLED: bool | None = None  # cached probe result


def internet_available(timeout: float = 2.0) -> bool:
    """Return True if a quick TCP connectivity probe succeeds.

    Result is cached for the process lifetime — repeated calls are cheap.
    Override via ``AGENT_INTERNET=on|off|auto`` (default 'auto').

    Probe target: 1.1.1.1:53 (Cloudflare DNS over TCP). Fast, doesn't
    require DNS resolution itself, doesn't depend on any specific HTTP
    service, doesn't leak telemetry to a search engine.
    """
    global _INTERNET_ENABLED
    if _INTERNET_ENABLED is not None:
        return _INTERNET_ENABLED

    setting = os.environ.get("AGENT_INTERNET", "auto").lower()
    if setting == "off":
        _INTERNET_ENABLED = False
        return False
    if setting == "on":
        _INTERNET_ENABLED = True
        return True

    # auto: probe
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            _INTERNET_ENABLED = True
            return True
    except (OSError, socket.timeout):
        _INTERNET_ENABLED = False
        return False


def reset_internet_cache() -> None:
    """Clear cached connectivity result. Useful for tests."""
    global _INTERNET_ENABLED
    _INTERNET_ENABLED = None


class _Args(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Search query.")
    max_results: int = Field(default=5, ge=1, le=20, description="How many URLs to return.")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)


class WebSearchTool(Tool[_Args]):
    name = "web_search"
    tier = 0
    description = (
        "Search the web for URLs related to a query. Returns a list of "
        "(title, url, snippet) tuples — typically 5. Pair with web_fetch to "
        "retrieve a chosen URL's content. OPTIONAL FEATURE: this tool fails "
        "cleanly when internet is disabled (AGENT_INTERNET=off) or "
        "unreachable. FAILURE MODES: internet_disabled; network_error; "
        "search_engine_blocked; timeout."
    )
    failure_modes = (
        "internet_disabled",
        "network_error",
        "search_engine_blocked",
        "timeout",
    )
    Args = _Args

    # DuckDuckGo HTML endpoint. No API key, no JS required.
    _DDG_URL = "https://html.duckduckgo.com/html/"
    _USER_AGENT = "Mozilla/5.0 (sovereign-agent web_search; +https://example.com)"

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        if not internet_available():
            return ToolResult(
                ok=False,
                error="internet access is disabled (AGENT_INTERNET=off) or unreachable",
            )

        try:
            async with httpx.AsyncClient(
                timeout=args.timeout_seconds,
                headers={"User-Agent": self._USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.post(
                    self._DDG_URL,
                    data={"q": args.query, "kl": "us-en"},
                )
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as e:
            return ToolResult(
                ok=False,
                error=f"search engine returned {e.response.status_code}",
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            return ToolResult(ok=False, error=f"network error: {type(e).__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"web_search failed: {type(e).__name__}: {e}")

        results = _parse_ddg_html(html, max_results=args.max_results)
        if not results:
            return ToolResult(
                ok=False,
                error="no results parsed (search engine may have changed format)",
            )

        return ToolResult(
            ok=True,
            output=results,
            metadata={
                "query": args.query,
                "result_count": len(results),
                "backend": "duckduckgo_html",
            },
        )


# DuckDuckGo HTML parsing. Brittle by definition — search engines change
# their HTML. Kept narrow and conservative: extract only what we need (link
# class identifies result-row anchors). If DDG changes their format this
# tool stops working; the failure is loud (zero results) and the operator
# can swap backend or update the parser.
_RESULT_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*?class="result__a"[^>]*?href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_RESULT_SNIPPET_RE = re.compile(
    r'<a\s+[^>]*?class="result__snippet"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_DDG_REDIR_RE = re.compile(r"^/?l/\?(?:.*&)?uddg=([^&]+)")


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s).replace("&amp;", "&").replace("&#x27;", "'").strip()


def _unwrap_ddg_redirect(href: str) -> str:
    """DDG wraps result links in their redirector. Unwrap to the real URL."""
    m = _DDG_REDIR_RE.match(href)
    if m:
        return unquote(m.group(1))
    return href


def _parse_ddg_html(html: str, *, max_results: int) -> list[dict]:
    """Extract (title, url, snippet) tuples from DDG HTML response."""
    anchors = _RESULT_ANCHOR_RE.findall(html)
    snippets = _RESULT_SNIPPET_RE.findall(html)
    out: list[dict] = []
    for i, (href, title_html) in enumerate(anchors):
        if i >= max_results:
            break
        url = _unwrap_ddg_redirect(href)
        # Skip ad/affiliate links if they snuck through
        if not url.startswith(("http://", "https://")):
            continue
        title = _strip_tags(title_html)
        snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
        out.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })
    return out
