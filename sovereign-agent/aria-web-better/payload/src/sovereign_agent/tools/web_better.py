"""
web_better.py — T0: clean web extraction and multi-hop research

web_fetch returns raw HTML. web_search returns titles and URLs. Neither gives
Aria clean, readable content. These tools close that gap.

Two tools:
  web_extract   (T0) — fetch a URL, return clean markdown (HTML → text)
  web_research  (T0) — search + extract top results → synthesized block

Domain allowlist: superset of web_fetch's defaults, expanded for docs/research.
Override via AGENT_FETCH_ALLOWLIST env var (comma-separated).

markdownify (pip install markdownify) is preferred for HTML→markdown.
Falls back to tag-stripping if not installed — still readable, less structured.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# ─── Domain allowlist ────────────────────────────────────────────────────────

_DEFAULT_ALLOWLIST: frozenset[str] = frozenset({
    # From web_fetch defaults
    "docs.python.org",
    "pypi.org",
    "github.com",
    "raw.githubusercontent.com",
    "wikipedia.org",
    "en.wikipedia.org",
    # New additions (docs + research)
    "stackoverflow.com",
    "developer.mozilla.org",
    "pypa.io",
    "readthedocs.io",
    "arxiv.org",
    "packaging.python.org",
    "docs.anthropic.com",
    "peps.python.org",
    "realpython.com",
    "python.org",
    "pip.pypa.io",
    "docs.pydantic.dev",
    "textual.textualize.io",
    "rich.readthedocs.io",
    "httpx.readthedocs.io",
    "sqlite.org",
    "docs.pytest.org",
    "mypy.readthedocs.io",
    "ruff.rs",
})


def _allowlist() -> frozenset[str]:
    raw = os.environ.get("AGENT_FETCH_ALLOWLIST", "")
    if raw:
        return frozenset(d.strip().lower() for d in raw.split(",") if d.strip())
    return _DEFAULT_ALLOWLIST


def _check_url(url: str) -> tuple[bool, str]:
    """Validate URL scheme and domain. Returns (ok, error_or_host)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "invalid URL"
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme: {parsed.scheme}"
    host = (parsed.hostname or "").lower()
    # Allow subdomains: stackoverflow.com covers stackoverflow.com itself
    allowed = _allowlist()
    if host not in allowed and not any(host.endswith("." + d) for d in allowed):
        return False, f"domain not in allowlist: {host}"
    return True, host


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")
_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|#39|nbsp|ndash|mdash);")
_ENTITY_MAP = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
    "&ndash;": "–", "&mdash;": "—",
}


def _html_to_text(html: str, max_chars: int = 8000) -> str:
    """HTML → clean readable text. Uses markdownify if available."""
    try:
        import markdownify
        text = markdownify.markdownify(html, heading_style="ATX", strip=["script", "style"])
    except ImportError:
        # Strip script/style blocks first
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = _TAG_RE.sub(" ", html)
        for ent, repl in _ENTITY_MAP.items():
            text = text.replace(ent, repl)
    # Normalize whitespace
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _WS_RE.sub("\n\n", text).strip()
    return text[:max_chars]


_USER_AGENT = "sovereign-agent/web_better (research; +https://example.com)"


# ─── WebExtractTool ──────────────────────────────────────────────────────────


class WebExtractTool(Tool):
    """Fetch a URL and return clean readable text (HTML stripped / markdownified).

    Better than web_fetch for reading content — strips boilerplate, converts
    HTML structure to readable text. Falls back to tag-stripping if the
    markdownify library is not installed.

    Args:
      url       — URL to fetch (must be on the expanded allowlist)
      max_chars — character cap on output (default 8000)
      timeout   — request timeout in seconds (default 15)

    Domain allowlist: superset of web_fetch defaults + common docs/research sites.
    Override all domains via AGENT_FETCH_ALLOWLIST env var.

    FAILURE MODES: domain_not_allowlisted, timeout, non_2xx, ssl_error, invalid_url.
    """

    name = "web_extract"
    tier = 0
    description = (
        "Fetch a URL and return clean readable text (HTML stripped to markdown/text). "
        "Args: url (str), max_chars (int default 8000), timeout (float default 15). "
        "Covers: github.com, docs.python.org, stackoverflow.com, wikipedia.org, arxiv.org, "
        "readthedocs.io, developer.mozilla.org, pypa.io + more. "
        "FAILURE MODES: domain_not_allowlisted, timeout, non_2xx, ssl_error, invalid_url."
    )
    failure_modes = ("domain_not_allowlisted", "timeout", "non_2xx", "ssl_error", "invalid_url")

    class Args(BaseModel):
        url: str = Field(description="URL to fetch and extract text from.")
        max_chars: int = Field(default=8000, ge=100, le=40000)
        timeout: float = Field(default=15.0, ge=1.0, le=60.0)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        ok, host_or_err = _check_url(args.url)
        if not ok:
            return ToolResult(ok=False, error=host_or_err)

        try:
            async with httpx.AsyncClient(
                timeout=args.timeout,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(args.url)
        except httpx.TimeoutException:
            return ToolResult(ok=False, error="timeout")
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=f"http error: {type(exc).__name__}: {exc}")

        if not (200 <= resp.status_code < 300):
            return ToolResult(ok=False, error=f"status {resp.status_code}")

        content_type = resp.headers.get("content-type", "")
        raw = resp.content[:500_000].decode("utf-8", errors="replace")

        if "html" in content_type or raw.lstrip().startswith("<"):
            text = _html_to_text(raw, args.max_chars)
        else:
            text = raw[:args.max_chars]

        return ToolResult(
            ok=True,
            output=text,
            metadata={
                "url": str(resp.url),
                "status": resp.status_code,
                "content_type": content_type,
                "chars": len(text),
            },
        )


# ─── WebResearchTool ─────────────────────────────────────────────────────────


class WebResearchTool(Tool):
    """Multi-hop web research: search → extract top results → synthesized block.

    Runs a DuckDuckGo search, fetches and extracts the top N results (skipping
    domains not on the allowlist), and returns a combined block with source
    attribution. Much more useful than a bare search for research tasks.

    Args:
      query   — research question or search terms
      depth   — number of results to fetch (1–5, default 3)
      focus   — optional narrowing hint appended to the query (e.g. "python docs")

    Returns: synthesized block with [Source N] markers and a source list.

    FAILURE MODES: search_failed, no_extractable_results, internet_disabled.
    """

    name = "web_research"
    tier = 0
    description = (
        "Search the web + extract top results into a synthesized block with sources. "
        "Args: query (str), depth (int 1-5, default 3), focus (str, optional qualifier). "
        "FAILURE MODES: search_failed, no_extractable_results, internet_disabled."
    )
    failure_modes = ("search_failed", "no_extractable_results", "internet_disabled")

    class Args(BaseModel):
        query: str = Field(description="Research question or search terms.")
        depth: int = Field(default=3, ge=1, le=5, description="Number of results to fetch.")
        focus: str = Field(default="", description="Optional qualifier appended to the query.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.tools.web_search import WebSearchTool

        effective_query = f"{args.query} {args.focus}".strip()

        search_tool = WebSearchTool()
        # Using internal execute directly to avoid double tool registration check
        search_result = await search_tool.execute(
            search_tool.Args(query=effective_query, max_results=min(args.depth * 2, 10)),
            trace_id=trace_id,
        )

        if not search_result.ok:
            return ToolResult(ok=False, error=f"search failed: {search_result.error}")

        candidates: list[dict] = search_result.output or []
        if not candidates:
            return ToolResult(ok=False, error="search returned no results")

        extract_tool = WebExtractTool()
        sections: list[str] = []
        sources: list[str] = []
        fetched = 0

        for item in candidates:
            if fetched >= args.depth:
                break
            url = item.get("url", "")
            title = item.get("title", url)
            snippet = item.get("snippet", "")

            ok_url, _ = _check_url(url)
            if not ok_url:
                continue

            try:
                er = await extract_tool.execute(
                    extract_tool.Args(url=url, max_chars=3000, timeout=10.0),
                    trace_id=trace_id,
                )
            except Exception:
                continue

            if er.ok and er.output:
                src_n = fetched + 1
                sections.append(
                    f"[Source {src_n}] {title}\n"
                    f"{er.output[:2000]}"
                )
                sources.append(f"  [{src_n}] {url}")
                fetched += 1
            elif snippet:
                src_n = fetched + 1
                sections.append(f"[Source {src_n}] {title}\n{snippet}")
                sources.append(f"  [{src_n}] {url}")
                fetched += 1

        if not sections:
            return ToolResult(ok=False, error="no extractable results for this query")

        body = "\n\n".join(sections)
        source_list = "\n".join(sources)
        output = (
            f"Research: {effective_query}\n"
            f"{'═' * 60}\n\n"
            f"{body}\n\n"
            f"{'─' * 60}\n"
            f"Sources:\n{source_list}"
        )

        return ToolResult(
            ok=True,
            output=output,
            metadata={
                "query": effective_query,
                "sources_fetched": fetched,
                "sources": sources,
            },
        )
