"""retailer-scrape-d (Kevin, 2026-07-27): "make it seem natural is
needed" — the hardened, session-persistent Playwright layer used by
ScrapeFetcher for Target/Best Buy/Pokémon Center."""
from __future__ import annotations

from sovereign_agent.discord_runtime.stealth_browser import (
    StealthSession,
    get_shared_session,
    looks_blocked,
    scrape_lock,
)


# ── looks_blocked (pure) ─────────────────────────────────────────────────────
def test_looks_blocked_on_error_status_codes():
    assert looks_blocked("some page", 403)
    assert looks_blocked("some page", 429)
    assert looks_blocked("some page", 503)


def test_looks_blocked_on_empty_body():
    assert looks_blocked("", 200)
    assert looks_blocked("   ", 200)


def test_looks_blocked_on_known_challenge_markers():
    assert looks_blocked("<html>Checking your browser before accessing...</html>", 200)
    assert looks_blocked("<div class='cf-browser-verification'>...</div>", 200)
    assert looks_blocked("Please complete the px-captcha to continue", 200)
    assert looks_blocked("PerimeterX blocked this request", 200)


def test_looks_blocked_false_for_a_real_content_page():
    assert not looks_blocked(
        "<html><body><h1>RTX 4070 Super - $529.99</h1><p>In stock</p></body></html>",
        200)


def test_looks_blocked_case_insensitive():
    assert looks_blocked("ACCESS DENIED", 200)
    assert looks_blocked("Unusual Traffic Detected", 200)


# ── StealthSession (real Playwright, no external network — data: URLs) ──────
def test_session_picks_a_consistent_identity():
    s = StealthSession()
    ua1, vp1 = s._ua, s._viewport
    # identity doesn't change between calls within the same session
    assert s._ua == ua1 and s._viewport == vp1
    from sovereign_agent.discord_runtime.stealth_browser import _UA_POOL, _VIEWPORTS
    assert ua1 in _UA_POOL
    assert vp1 in _VIEWPORTS


def test_session_visits_a_data_url_and_reads_content():
    s = StealthSession()
    try:
        html, status = s.visit(
            "data:text/html,<html><body><h1>hello natural world</h1></body></html>")
        assert status == 200
        assert "hello natural world" in html
        assert not looks_blocked(html, status)
    finally:
        s.close()


def test_session_persists_across_multiple_visits():
    """The core 'natural' fix: one context AND page survive multiple
    .visit() calls, unlike browser.py's per-call launch+close."""
    s = StealthSession()
    try:
        s.visit("data:text/html,<html><body>first</body></html>")
        context_after_first, page_after_first = s._context, s._page
        s.visit("data:text/html,<html><body>second</body></html>")
        assert s._context is context_after_first    # same context, not relaunched
        assert s._page is page_after_first           # same page, not recreated
    finally:
        s.close()


def test_visit_survives_an_unreachable_url_never_raises():
    # a well-formed https URL to a domain that can't exist — real Source
    # URLs are always valid https, so this (not a malformed scheme, which
    # browsers handle non-deterministically) is the realistic failure
    # case worth guaranteeing never raises.
    s = StealthSession()
    try:
        html, status = s.visit(
            "https://this-domain-does-not-exist-abcxyz123.invalid/",
            timeout_ms=3000)
        assert isinstance(html, str) and isinstance(status, int)
        assert status != 200
    finally:
        s.close()


def test_warm_up_visits_the_homepage_once_per_new_host():
    """Live-verified to matter against Pokémon Center: a cold direct hit
    to a deep page got challenged even via Firefox; landing on the
    homepage first, same page, cleared it once. Unit-tested here with a
    fake page (no real browser) since the mechanism itself is what's
    worth guaranteeing, independent of any one site's live behavior."""
    s = StealthSession()
    visited = []

    class _FakePage:
        def goto(self, url, **kw):
            visited.append(url)

    page = _FakePage()
    s._warm_up(page, "https://example.com/deep/page", 5000, (0.0, 0.0))
    assert visited == ["https://example.com/"]

    # a second visit to the SAME host doesn't warm up again
    s._warm_up(page, "https://example.com/another/page", 5000, (0.0, 0.0))
    assert visited == ["https://example.com/"]

    # a DIFFERENT host warms up separately
    s._warm_up(page, "https://other.example/page", 5000, (0.0, 0.0))
    assert visited == ["https://example.com/", "https://other.example/"]


def test_warm_up_skips_when_the_target_is_already_the_homepage():
    s = StealthSession()
    visited = []

    class _FakePage:
        def goto(self, url, **kw):
            visited.append(url)

    s._warm_up(_FakePage(), "https://example.com/", 5000, (0.0, 0.0))
    assert visited == []


def test_get_shared_session_is_a_singleton():
    a = get_shared_session()
    b = get_shared_session()
    assert a is b


def test_scrape_lock_is_reentrant_safe_module_level_lock():
    lock = scrape_lock()
    acquired = lock.acquire(blocking=False)
    assert acquired
    lock.release()
