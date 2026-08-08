"""browser.py — Stateful web browsing session for Aria (M50).

Primary backend: httpx (already in venv, zero VRAM, stateful cookies).
Optional enhancement: playwright for JS-rendered pages (install separately).

Pattern mirrors voice.py / vision.py: CPU-first, graceful fallback.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse


# ── HTML parsing utilities ────────────────────────────────────────────────────


class _TextExtractor(HTMLParser):
    """Extract human-readable text from HTML, stripping tags and scripts."""

    # Only non-void elements that wrap text we want to skip.
    # meta/link are void elements (no </tag>) — excluding them avoids stuck skip counter.
    _SKIP_TAGS = {"script", "style", "head", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip > 0:
            self._skip -= 1
        elif tag.lower() in ("p", "div", "h1", "h2", "h3", "li", "br", "tr"):
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip == 0:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def get_text(self) -> str:
        raw = " ".join(self._chunks)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return html.unescape(raw).strip()


class _LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base = base_url
        self.links: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attr_dict = dict(attrs)
            href = attr_dict.get("href", "")
            text = attr_dict.get("title", "")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                full = urljoin(self._base, href)
                self.links.append({"href": full, "text": text})

    def handle_data(self, data):
        if self.links and not self.links[-1]["text"]:
            stripped = data.strip()
            if stripped:
                self.links[-1]["text"] = stripped[:120]


def _extract_title(html_text: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    return html.unescape(m.group(1).strip()) if m else ""


def html_to_text(html_text: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html_text)
        return parser.get_text()[:20_000]
    except Exception:  # noqa: BLE001
        return html_text[:5000]


def extract_links(html_text: str, base_url: str) -> list[dict]:
    parser = _LinkExtractor(base_url)
    try:
        parser.feed(html_text)
        return parser.links[:50]
    except Exception:  # noqa: BLE001
        return []


# ── BrowserSession ────────────────────────────────────────────────────────────


class PageResult:
    def __init__(
        self,
        url: str,
        status_code: int,
        html_content: str,
        fetched_at: str,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.html_content = html_content
        self.fetched_at = fetched_at
        self._title = _extract_title(html_content)

    @property
    def title(self) -> str:
        return self._title

    @property
    def text(self) -> str:
        return html_to_text(self.html_content)

    @property
    def links(self) -> list[dict]:
        return extract_links(self.html_content, self.url)

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "status_code": self.status_code,
            "fetched_at": self.fetched_at,
            "text_length": len(self.text),
            "link_count": len(self.links),
        }


class BrowserSession:
    """Stateful HTTP browsing session. Persists cookies across navigate() calls.

    Uses httpx for static pages. Optional playwright for JS-rendered pages
    (requires: pip install playwright && playwright install chromium).
    """

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self) -> None:
        self._current: Optional[PageResult] = None
        self._history: list[str] = []
        self._httpx_client = None

    def _get_client(self):
        if self._httpx_client is None:
            import httpx  # noqa: PLC0415
            self._httpx_client = httpx.Client(
                headers=self._HEADERS,
                follow_redirects=True,
                timeout=15.0,
            )
        return self._httpx_client

    def navigate(self, url: str, js_render: bool = False) -> PageResult:
        """Fetch a URL. If js_render=True and playwright available, use Chromium.

        Playwright renders JavaScript (SPAs, dynamic pages). httpx handles
        static HTML faster. Choose based on target site's needs.
        """
        if js_render and self.playwright_available():
            return self._navigate_playwright(url)
        return self._navigate_httpx(url)

    def _navigate_httpx(self, url: str) -> PageResult:
        client = self._get_client()
        response = client.get(url)
        ts = datetime.now(timezone.utc).isoformat()
        content_type = response.headers.get("content-type", "")
        if "html" in content_type:
            html_content = response.text
        else:
            html_content = f"<pre>{response.text[:10_000]}</pre>"
        page = PageResult(
            url=str(response.url),
            status_code=response.status_code,
            html_content=html_content,
            fetched_at=ts,
        )
        self._current = page
        self._history.append(str(response.url))
        return page

    def _navigate_playwright(self, url: str) -> PageResult:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        ts = datetime.now(timezone.utc).isoformat()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=self._HEADERS["User-Agent"],
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            html_content = page.content()
            final_url = page.url
            status = response.status if response else 200
            browser.close()
        result = PageResult(
            url=final_url,
            status_code=status,
            html_content=html_content,
            fetched_at=ts,
        )
        self._current = result
        self._history.append(final_url)
        return result

    def current(self) -> Optional[PageResult]:
        return self._current

    def history(self) -> list[str]:
        return list(self._history)

    def clear(self) -> None:
        self._current = None
        self._history.clear()
        if self._httpx_client:
            self._httpx_client.close()
            self._httpx_client = None

    @staticmethod
    def playwright_available() -> bool:
        try:
            import playwright  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────


_browser_session: Optional[BrowserSession] = None


def get_browser_session() -> BrowserSession:
    global _browser_session
    if _browser_session is None:
        _browser_session = BrowserSession()
    return _browser_session
