"""stealth_browser.py — a hardened, session-persistent Playwright layer
for direct-retailer scraping (Target, Best Buy, Pokémon Center).

retailer-scrape-d (Kevin, 2026-07-27): "make it seem natural is needed."
Playwright is already a project dependency (browser.py's generic agent
tool); this module is a SEPARATE, heavier, scraper-specific layer,
lazily imported only when a `scrape`-kind Source is actually fetched —
the rest of the tracker fleet never needs Playwright at all.

What "natural" means here, concretely — hand-ported from crawlee-master
(Apache 2.0, read for design ideas only; no Node runtime, no literal
crawlee code, no Camoufox) PLUS live findings against the real sites:
  • Firefox, not Chromium, as the engine — live-verified: Chromium got an
    immediate DataDome challenge on 100% of attempts against Pokémon
    Center (a CDP-automation fingerprint tell), Firefox cleared the
    homepage consistently and the deeper search page intermittently.
    Genuinely better, not a solved problem — see `StealthSession`'s
    docstring for the full finding.
  • ONE browser context AND page persist across multiple visits.
    `browser.py`'s existing Playwright path launches+closes a fresh
    browser on EVERY call — a real visitor doesn't show up cookie-less
    every time; that statelessness is itself a strong automation signal.
  • a homepage warm-up on the first visit to any new host, live-verified
    to matter — a cold direct hit to a deep page got challenged even via
    Firefox; landing on the homepage first, same page, then navigating
    to the real target, cleared it (once — see the honesty note above).
  • a hand-written stealth init script patches `navigator.webdriver` (the
    one automation tell Playwright sets on every engine) — deliberately
    not the third-party `playwright-stealth` package, matching this
    session's "hand-port the ideas, not the library" precedent already
    set for crawlee itself. Deliberately NOT patching Chromium-specific
    tells (window.chrome, WebGL vendor strings) now that the engine is
    Firefox — those would be wrong-engine signals, worse than no patch.
  • one fixed, realistic viewport+UA per SESSION (not per-request — a
    real user doesn't change screen size mid-visit).
  • a jittered dwell time after page load before reading content.
  • serialized: one scrape session active at a time, process-wide (a
    background duty loop must never pile up concurrent headless-browser
    instances — the same discipline `vram.py`'s `vram_lock` applies to
    other heavy tools, even though this isn't VRAM).

Even hardened, this does NOT reliably clear Cloudflare/Akamai/PerimeterX-
grade managed challenges — crawlee's own docs concede that tier needs a
hardened browser BUILD (Camoufox) plus literal challenge-solving
interaction, not just fingerprint patches, and live testing here confirms
it: Pokémon Center cleared once, not consistently. `looks_blocked()`
below detects when a challenge page slipped through anyway, feeding the
SAME per-host cooldown `fetchers.py` already built for HTTP 429/503 — a
detected block backs off exactly like a real rate limit, never hammered.
"""
from __future__ import annotations

import random
import threading
import time

__all__ = ["StealthSession", "get_shared_session", "scrape_lock", "looks_blocked"]

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 "
    "Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 "
    "Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Hand-written stealth patches, Firefox-correct: `navigator.webdriver` is
# the one automation tell Playwright sets on EVERY engine (Firefox
# included) — worth patching universally. Deliberately NOT porting the
# `window.chrome`/WebGL-vendor patches that were in an earlier Chromium-
# targeted draft of this file: real Firefox never has `window.chrome` at
# all, and Firefox's WebGL vendor strings differ from Chromium's — adding
# either would be a wrong-engine tell, worse than no patch at all.
_STEALTH_INIT_JS = r"""
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
"""

# Challenge/block page markers — Cloudflare/Akamai/PerimeterX/Incapsula.
# Deliberately broad + case-insensitive: a false positive just costs one
# extra skip, never a hammered retry.
_BLOCK_MARKERS = (
    "just a moment", "checking your browser", "cf-browser-verification",
    "cf-chl-", "px-captcha", "_incapsula_resource", "attention required",
    "access denied", "verify you are a human", "unusual traffic",
    "captcha-delivery.com", "perimeterx",
)


def looks_blocked(html: str, status: int) -> bool:
    """A challenge/block page often returns HTTP 200 with a JS puzzle
    body, not an error code — status-only detection would miss it, so
    this always scans the body too."""
    if status in (403, 429, 503):
        return True
    text = (html or "").lower()
    if not text.strip():
        return True                     # an empty body is itself a signal
    return any(marker in text for marker in _BLOCK_MARKERS)


class StealthSession:
    """One persistent, hardened Playwright browser context — AND one
    persistent page, reused across visits, not recreated each time. NOT
    thread-safe by itself — callers serialize via `scrape_lock()`.

    Engine: Firefox, not Chromium — live-verified against Pokémon Center
    (Kevin's stated main goal, 2026-07-27) to matter, though NOT to be a
    reliable fix: a bare `curl` from this same network got HTTP 200
    every time; Playwright's Chromium got an immediate DataDome
    challenge (captcha-delivery.com) on 100% of attempts, homepage
    included — a CDP-automation-fingerprint tell, not an IP-reputation
    block. Playwright's Firefox engine cleared the homepage consistently
    and cleared the search page ONCE out of several attempts — genuinely
    better than Chromium (which never once got through), but still
    intermittent, not solved. Crawlee's own docs point at this exact
    class of problem for Cloudflare/Akamai/PerimeterX-tier sites and
    recommend Camoufox (a more deeply patched Firefox) over stock
    browsers for exactly this reason — this uses stock Playwright
    Firefox, a real but partial step in that direction. Treat Pokémon
    Center coverage as best-effort, by design, not as delivered.

    Also live-verified (separately from the reliability question above):
    a cold direct hit to a deep page (e.g. a search URL) got challenged
    even via Firefox; visiting the SITE'S HOMEPAGE first, on the SAME
    page object, then navigating to the real target
    URL, cleared it — a natural referer/session chain, not a random
    guess. `visit()` does this automatically per new host."""

    def __init__(self, *, headless: bool = True, engine: str = "firefox") -> None:
        self._headless = headless
        self._engine = engine
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._warmed_hosts: set[str] = set()
        seed = random.randrange(len(_UA_POOL))
        self._ua = _UA_POOL[seed]
        self._viewport = _VIEWPORTS[seed % len(_VIEWPORTS)]

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        self._playwright = sync_playwright().start()
        engine = getattr(self._playwright, self._engine)
        self._browser = engine.launch(headless=self._headless)
        self._context = self._browser.new_context(
            user_agent=self._ua, viewport=self._viewport, locale="en-US")
        self._context.add_init_script(_STEALTH_INIT_JS)
        self._page = self._context.new_page()
        return self._page

    def _warm_up(self, page, url: str, timeout_ms: int,
                settle_s: tuple[float, float]) -> None:
        """First-ever visit to a new host: land on the homepage before
        the real target — a natural referer/session chain, live-verified
        to matter (see class docstring)."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc
            homepage = f"{parsed.scheme}://{host}/"
            if not host or host in self._warmed_hosts or homepage == url:
                return
            page.goto(homepage, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(random.uniform(*settle_s))
            self._warmed_hosts.add(host)
        except Exception:  # noqa: BLE001 — a failed warm-up never blocks the real visit
            pass

    def visit(self, url: str, *, timeout_ms: int = 20_000,
              settle_s: tuple[float, float] = (1.5, 3.5)) -> tuple[str, int]:
        """Returns (html, status). Never raises — a broken page/timeout
        reports a synthetic 0 status (a failure to the caller, never a
        crash to the poll loop).

        target-parser-d (Kevin, 2026-07-27): live-diagnosed a real
        hydration race on target.com — `domcontentloaded` fires while a
        product card's WRAPPER markup already exists in the DOM but its
        title/price sub-elements haven't finished a client-side re-render
        yet, so a too-short dwell sometimes captures an incomplete card
        (harmless: the parser's own "no cards matched" fallback catches
        it honestly) instead of the real data that's one beat away.
        Widened from (0.8, 2.2) — a background poll loop isn't
        latency-sensitive, so trading a little speed for a better hit
        rate is a clean win, and it costs every scrape target the same
        extra second or two, not just Target's."""
        try:
            page = self._ensure_page()
            self._warm_up(page, url, timeout_ms, settle_s)
            response = page.goto(url, wait_until="domcontentloaded",
                                 timeout=timeout_ms)
            time.sleep(random.uniform(*settle_s))   # natural dwell
            html = page.content()
            status = response.status if response else 200
            return html, status
        except Exception:  # noqa: BLE001 — a flaky page must never crash the loop
            return "", 0

    def close(self) -> None:
        try:
            if self._page is not None:
                self._page.close()
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._page = self._context = self._browser = self._playwright = None


_SHARED_LOCK = threading.Lock()
_SHARED_SESSION: StealthSession | None = None


def get_shared_session() -> StealthSession:
    """One shared session for the whole process — lazily created, kept
    alive across calls (the persistence that makes this "natural")."""
    global _SHARED_SESSION
    if _SHARED_SESSION is None:
        with _SHARED_LOCK:
            if _SHARED_SESSION is None:
                _SHARED_SESSION = StealthSession()
    return _SHARED_SESSION


def scrape_lock() -> threading.Lock:
    """Hold this for the full duration of a `.visit()` call — serializes
    scraping process-wide (a background duty loop must never pile up
    concurrent headless-Chromium instances)."""
    return _SHARED_LOCK
