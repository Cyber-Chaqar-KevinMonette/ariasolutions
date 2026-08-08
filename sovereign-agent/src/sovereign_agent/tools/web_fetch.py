"""web_fetch — Tier 0. HTTP GET with domain allowlist."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _allowlist() -> set[str]:
    """Domains the agent is permitted to fetch.

    Source of truth: $AGENT_FETCH_ALLOWLIST env var (comma-separated). Defaults
    to a conservative set. Operator can override via env or config file.
    """
    raw = os.environ.get("AGENT_FETCH_ALLOWLIST")
    if raw:
        return {d.strip().lower() for d in raw.split(",") if d.strip()}
    return {
        "docs.python.org",
        "pypi.org",
        "github.com",
        "raw.githubusercontent.com",
        "wikipedia.org",
        "en.wikipedia.org",
    }


class _Args(BaseModel):
    url: str = Field(description="Full URL (http/https). Domain must be allowlisted.")
    max_bytes: int = Field(default=500_000, ge=1, le=5_000_000)
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)


class WebFetchTool(Tool[_Args]):
    name = "web_fetch"
    tier = 0
    description = (
        "HTTP GET a URL on the allowlist. Returns body as text (truncated at "
        "max_bytes) plus status code and content-type. FAILURE MODES: domain not "
        "in allowlist; timeout; non-2xx status; SSL error; response exceeds "
        "max_bytes (truncated, returns partial)."
    )
    failure_modes = (
        "domain_not_allowlisted",
        "timeout",
        "non_2xx",
        "ssl_error",
        "size_truncated",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            parsed = urlparse(args.url)
        except ValueError as e:
            return ToolResult(ok=False, error=f"invalid URL: {e}")

        if parsed.scheme not in ("http", "https"):
            return ToolResult(ok=False, error=f"unsupported scheme: {parsed.scheme}")
        host = (parsed.hostname or "").lower()
        if host not in _allowlist():
            return ToolResult(
                ok=False,
                error=f"domain not in allowlist: {host}",
            )

        try:
            async with httpx.AsyncClient(
                timeout=args.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "sovereign-agent/0.1"},
            ) as client:
                resp = await client.get(args.url)
        except httpx.TimeoutException:
            return ToolResult(ok=False, error="timeout")
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=f"http error: {type(e).__name__}: {e}")

        body = resp.content[: args.max_bytes]
        truncated = len(resp.content) > args.max_bytes
        try:
            text = body.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            text = body.decode("latin-1", errors="replace")

        ok = 200 <= resp.status_code < 300
        return ToolResult(
            ok=ok,
            output=text if ok else None,
            error=None if ok else f"status {resp.status_code}",
            metadata={
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type"),
                "truncated": truncated,
                "url": str(resp.url),
            },
        )
