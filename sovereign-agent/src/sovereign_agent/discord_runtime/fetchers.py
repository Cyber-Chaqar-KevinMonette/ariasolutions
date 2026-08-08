"""fetchers — turn a Source into Items. Five real fetchers behind the
`Fetcher` protocol, plus a `fetcher_for` factory that picks by
`source.kind` (and, for reddit.com, by domain):

  • `RssFetcher`    — RSS 2.0 + Atom via stdlib `xml.etree` (no feedparser
                       dependency). Items keyed on guid/id/link.
  • `RedditFetcher` — reddit-oauth-d (Kevin, 2026-07-27): "no alerts yet" —
                       confirmed root cause was every reddit.com RSS source
                       tripping the anonymous endpoint's rate limit (HTTP
                       429, ×9-35 in a row, fleet-wide, per bot_health
                       telemetry). Authenticated via Reddit's official
                       client-credentials OAuth (shared exchange lives in
                       credentials.reddit_client_credentials_token — one
                       implementation, not two) whenever REDDIT_CLIENT_ID/
                       SECRET are vaulted; falls back to RssFetcher's
                       anonymous path otherwise. Never a hard dependency.
  • `HttpJsonFetcher` (in sources.py) — JSON/API endpoints.
  • `ChangeFetcher` — fetch bytes, key an Item on their hash. Change
                       detection needs no extra state: an unchanged page
                       hashes the same, so the runtime's own dedup suppresses
                       it, and a changed page produces exactly one new alert.
                       (The high-leverage trick: let dedup do the work.)
  • `ScrapeFetcher`  — retailer-scrape-d (Kevin, 2026-07-27): "I tried
                       official APIs but decided to try our own
                       scraping." Direct browser-based fetch (Target,
                       Best Buy, Pokémon Center — no reliable RSS/API
                       lane) via the hardened `stealth_browser.py`
                       session, lazily imported so Playwright is never a
                       hard requirement for the rest of the fleet. Reuses
                       this module's own per-host cooldown mechanism: a
                       detected block backs off exactly like a real
                       429/503, never hammered. No guaranteed success
                       against Cloudflare/Akamai/PerimeterX-grade bot
                       management — best-effort, by design.

Every fetcher takes an injectable `opener` (or, for ScrapeFetcher, a
`session`) so the network path is fully testable without a live network,
and swallows its own errors so one flaky source can never crash the poll
loop (the circuit breaker handles repeat failures upstream).
"""
from __future__ import annotations

import hashlib
import json as _json
import random as _random
import re as _re
from typing import Callable
from xml.etree import ElementTree as ET

from .sources import HttpJsonFetcher, Item, NullFetcher, Source

__all__ = ["RssFetcher", "RedditFetcher", "ChangeFetcher", "ScrapeFetcher",
           "register_scrape_parser", "WarframeFlipFetcher", "fetcher_for"]

_ATOM = "{http://www.w3.org/2005/Atom}"


# rate-limit-d (Kevin): space same-host requests so we stay inside each
# source's limits. Reddit throttles unauthenticated readers hard (HTTP 429),
# and the fleet has ~36 reddit sources — without pacing they trip the limit
# and nothing posts. A monotonic per-host clock + a short sleep fixes it;
# the duty loop is a background service, so a paced fetch pass is fine.
import threading as _threading
import time as _time
from urllib.parse import urlparse as _urlparse

_HOST_LAST: dict[str, float] = {}
_HOST_LOCK = _threading.Lock()
_HOST_MIN_INTERVAL = {
    "www.reddit.com": 2.5, "reddit.com": 2.5, "old.reddit.com": 2.5,
    # reddit-oauth-d: authenticated calls get a real, generous per-app
    # limit (~100 req/min) — still paced, just far less conservatively
    # than the anonymous endpoint above.
    "oauth.reddit.com": 0.6,
    # warframe-flip-d: a real, official, no-auth API built for exactly
    # this use case — no rate-limit wall found, but paced anyway (good
    # citizen, not "no limit exists").
    "api.warframe.market": 0.4,
    # vaulted-relics-d: WFCD's community drop-table host — same
    # good-citizen pacing, not fetched per-tick (cached, 3 days).
    "drops.warframestat.us": 0.4,
}
_DEFAULT_MIN_INTERVAL = 0.25

def _throttle(url: str) -> None:
    """Sleep just enough to keep same-host requests politely spaced."""
    try:
        host = _urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return
    gap = _HOST_MIN_INTERVAL.get(host, _DEFAULT_MIN_INTERVAL)
    with _HOST_LOCK:
        now = _time.monotonic()
        wait = gap - (now - _HOST_LAST.get(host, 0.0))
        if wait > 0:
            _time.sleep(min(wait, gap))          # bounded
            now = _time.monotonic()
        _HOST_LAST[host] = now


# crawlee-hand-port-d (Kevin, 2026-07-27): "rate limit each channel also
# so we don't run into this again" — a technique hand-ported from
# crawlee-master (the JS anti-blocking scraper Kevin dropped for review)
# as plain Python, no new runtime/dependency: exponential backoff-as-
# cooldown on 429/503, per-host. A host that's actively blocking us gets
# SKIPPED for a growing window (bounded) instead of retried at the same
# fixed cadence forever; a success halves the window back down (gradual
# recovery). This is a skip, never a sleep — a background poll tick must
# stay fast and non-blocking, so pacing on this timescale (a multi-minute
# cooldown) comes from skipping the attempt and letting the next tick
# retry, never a long inline `time.sleep()` that would stall the whole
# tick (and every OTHER source sharing it).
_HOST_BACKOFF: dict[str, float] = {}
_HOST_COOLDOWN_UNTIL: dict[str, float] = {}
_BACKOFF_BASE_S = 5.0
_BACKOFF_CAP_S = 120.0


def _note_outcome(url: str, ok: bool, code: int | None) -> None:
    """A 429/503 grows this host's cooldown window exponentially (capped);
    anything else halves it back down — cautious recovery, not an instant
    reset. Never sleeps here — only ever sets a "skip until" timestamp."""
    try:
        host = _urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return
    with _HOST_LOCK:
        if not ok and code in (429, 503):
            cur = _HOST_BACKOFF.get(host, 0.0)
            nxt = min(_BACKOFF_CAP_S, max(_BACKOFF_BASE_S, cur * 2))
            _HOST_BACKOFF[host] = nxt
            _HOST_COOLDOWN_UNTIL[host] = _time.monotonic() + nxt
        elif host in _HOST_BACKOFF:
            _HOST_BACKOFF[host] = _HOST_BACKOFF[host] / 2.0
            if _HOST_BACKOFF[host] < 0.5:
                del _HOST_BACKOFF[host]


def _cooldown_remaining(url: str) -> float:
    """>0 → skip this fetch entirely, this many seconds of post-429/503
    cooldown remain for this host. Never sleeps for it."""
    try:
        host = _urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return 0.0
    with _HOST_LOCK:
        until = _HOST_COOLDOWN_UNTIL.get(host, 0.0)
    return max(0.0, until - _time.monotonic())


# Note: a Source's own `allowed_min_interval_s` (sources.py) is
# deliberately NOT re-enforced here at the individual fetch call — it's
# already validated at the project poll-loop layer (runtime.py's
# Contract.validate_for_source), which is the correct scope for "how
# often does this whole project's tick run." Re-checking it per raw fetch
# call would make every repeated `.fetch()` call skip until the interval
# elapses — including in tests and any direct/manual re-fetch — which
# conflicts with the fetcher layer's existing contract (a fetch call
# always really attempts the fetch). The per-host 429/503 cooldown above
# is the layer that actually needed adding here.


# crawlee-hand-port-d: a short pool of realistic browser signatures for
# anonymous fetches — rotated per request so a single fixed UA isn't the
# only fingerprint every source shares. Each still carries our own
# identifying token, same honesty stance as before ("a real feed reader,
# not a scraper evading anything") — the browser portion varies, the
# identification doesn't.
_UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 BigKevsBotShop-Scout/1.0 (+feed reader)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
    "like Gecko) Chrome/123.0.0.0 Safari/537.36 BigKevsBotShop-Scout/1.0 "
    "(+feed reader)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15 "
    "BigKevsBotShop-Scout/1.0 (+feed reader)",
]


def _pick_ua() -> str:
    return _random.choice(_UA_POOL)


def _read(opener: Callable | None, url: str, timeout: float,
          *, source: Source | None = None) -> tuple[bytes | None, str]:
    """Fetch bytes. Returns (data, "") on success or (None, error_detail).
    Never raises — a flaky source must never crash the loop; the detail is
    what makes link-rot VISIBLE instead of silent (R5a)."""
    if not url:
        return None, "no url configured"
    cooldown = _cooldown_remaining(url)             # post-429/503 backoff
    if cooldown > 0:
        return None, f"backing off {cooldown:.0f}s after repeated 429/503"
    _throttle(url)                                # rate-limit-d: polite pacing
    if opener is None:  # lazy: only touch the network when truly used
        from urllib.request import Request, urlopen

        def opener(u, timeout):  # type: ignore[misc]
            # verticals-d: public deal/RSS feeds (Slickdeals, Reddit) block
            # the default Python-urllib UA with 403/429. An identifying,
            # browser-shaped UA is accepted and honest — we're a real feed
            # reader, not a scraper evading anything.
            req = Request(u, headers={
                "User-Agent": _pick_ua(),
                "Accept": "application/rss+xml, application/atom+xml, "
                          "application/xml, text/xml, */*"})
            return urlopen(req, timeout=timeout)
    try:
        with opener(url, timeout=timeout) as resp:  # type: ignore[misc]
            data = resp.read()
        _note_outcome(url, True, None)
        return data, ""
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)          # urllib HTTPError carries .code
        _note_outcome(url, False, code)
        if code is not None:
            return None, f"HTTP {code}"
        return None, type(exc).__name__


def _report(on_outcome, source: Source, ok: bool, detail: str) -> None:
    """Fire the outcome hook; a broken hook must never break a fetch."""
    if on_outcome is None:
        return
    try:
        on_outcome(source.name, ok, detail)
    except Exception:  # noqa: BLE001
        pass


class RssFetcher:
    """Parse RSS 2.0 or Atom feeds with the standard library only."""

    def __init__(self, opener: Callable | None = None, timeout: float = 10.0,
                 max_items: int = 25, on_outcome: Callable | None = None) -> None:
        self._opener = opener
        self._timeout = timeout
        self._max_items = max_items
        self._on_outcome = on_outcome

    def fetch(self, source: Source) -> list[Item]:
        raw, err = _read(self._opener, source.url, self._timeout, source=source)
        if raw is None:
            _report(self._on_outcome, source, False, err)
            return []
        try:
            root = ET.fromstring(raw)
        except Exception:  # noqa: BLE001
            _report(self._on_outcome, source, False, "unparseable feed (not XML)")
            return []
        items = self._parse_rss(root) or self._parse_atom(root)
        _report(self._on_outcome, source, True, f"{len(items)} item(s)")
        return items[: self._max_items]

    @staticmethod
    def _text(el, default: str = "") -> str:
        return (el.text or default).strip() if el is not None else default

    def _parse_rss(self, root) -> list[Item]:
        out: list[Item] = []
        for item in root.iter("item"):
            title = self._text(item.find("title"))
            guid = self._text(item.find("guid"))
            link = self._text(item.find("link"))
            ident = guid or link or title
            # scout-d: keep the real deal URL even when guid is the dedup key
            url = link if link.startswith("http") else (
                ident if ident.startswith("http") else "")
            if ident:
                out.append(Item(id=ident, text=title or ident, url=url))
        return out

    def _parse_atom(self, root) -> list[Item]:
        out: list[Item] = []
        for entry in root.iter(f"{_ATOM}entry"):
            title = self._text(entry.find(f"{_ATOM}title"))
            ident = self._text(entry.find(f"{_ATOM}id"))
            href = ""
            link = entry.find(f"{_ATOM}link")
            if link is not None:
                href = link.get("href", "")
            if not ident:
                ident = href
            ident = ident or title
            url = href if href.startswith("http") else (
                ident if ident.startswith("http") else "")
            if ident:
                out.append(Item(id=ident, text=title or ident, url=url))
        return out


_REDDIT_HOSTS = {"www.reddit.com", "reddit.com", "old.reddit.com"}
_REDDIT_UA = "BigKevsBotShop-Scout/1.0 (official API; +ariasolutions.org)"
_REDDIT_SUB_RE = _re.compile(r"/r/([^/]+)/(new|hot|top|rising)?", _re.IGNORECASE)

_REDDIT_TOKEN: dict = {}
_REDDIT_TOKEN_LOCK = _threading.Lock()


def _is_reddit_url(url: str) -> bool:
    try:
        return _urlparse(url).netloc.lower() in _REDDIT_HOSTS
    except Exception:  # noqa: BLE001
        return False


def _reddit_sub_and_sort(url: str) -> tuple[str, str] | None:
    """'https://www.reddit.com/r/deals/new/.rss' -> ('deals', 'new')."""
    m = _REDDIT_SUB_RE.search(url or "")
    if not m:
        return None
    return m.group(1), (m.group(2) or "new").lower()


def _reddit_bearer_token(opener: Callable | None = None) -> str | None:
    """Cached OAuth bearer token — refreshed once it's near expiry. Returns
    None (never raises) when creds aren't vaulted or the exchange fails;
    callers fall back to the anonymous RSS path in that case."""
    with _REDDIT_TOKEN_LOCK:
        now = _time.monotonic()
        if _REDDIT_TOKEN.get("access_token") and now < _REDDIT_TOKEN.get("expires_at", 0.0):
            return _REDDIT_TOKEN["access_token"]
        try:
            from sovereign_agent.credentials import (read_env,
                                                      reddit_client_credentials_token)
            env = read_env()
            cid = (env.get("REDDIT_CLIENT_ID") or "").strip()
            secret = (env.get("REDDIT_CLIENT_SECRET") or "").strip()
            if not cid or not secret:
                return None
            body, _detail = reddit_client_credentials_token(
                cid, secret, opener=opener)
        except Exception:  # noqa: BLE001 — a broken vault never crashes a fetch
            return None
        if not body:
            return None
        _REDDIT_TOKEN["access_token"] = body["access_token"]
        _REDDIT_TOKEN["expires_at"] = now + max(
            60, int(body.get("expires_in", 3600)) - 60)
        return _REDDIT_TOKEN["access_token"]


def _read_bearer(opener: Callable | None, url: str, timeout: float,
                 token: str, *, source: Source | None = None) -> tuple[bytes | None, str]:
    """Like `_read`, but with the Authorization: Bearer header oauth.reddit.com
    requires — kept separate so the anonymous `_read` path stays untouched."""
    cooldown = _cooldown_remaining(url)
    if cooldown > 0:
        return None, f"backing off {cooldown:.0f}s after repeated 429/503"
    _throttle(url)
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, timeout):  # type: ignore[misc]
            req = Request(u, headers={"Authorization": f"Bearer {token}",
                                      "User-Agent": _REDDIT_UA})
            return urlopen(req, timeout=timeout)
    try:
        with opener(url, timeout=timeout) as resp:  # type: ignore[misc]
            data = resp.read()
        _note_outcome(url, True, None)
        return data, ""
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        _note_outcome(url, False, code)
        if code is not None:
            return None, f"HTTP {code}"
        return None, type(exc).__name__


class RedditFetcher:
    """Authenticated Reddit JSON listing — the fix for reddit-oauth-d
    (Kevin, 2026-07-27): "no alerts yet," root-caused to every reddit.com
    RSS source tripping the anonymous endpoint's rate limit fleet-wide.
    Falls back to `RssFetcher`'s anonymous path whenever no OAuth token is
    available (creds not vaulted, or the exchange fails) — never a hard
    dependency."""

    def __init__(self, opener: Callable | None = None, timeout: float = 10.0,
                 max_items: int = 25, on_outcome: Callable | None = None,
                 token_opener: Callable | None = None) -> None:
        self._opener = opener
        self._timeout = timeout
        self._max_items = max_items
        self._on_outcome = on_outcome
        self._token_opener = token_opener
        self._rss_fallback = RssFetcher(opener=opener, timeout=timeout,
                                        max_items=max_items,
                                        on_outcome=on_outcome)

    def fetch(self, source: Source) -> list[Item]:
        parsed = _reddit_sub_and_sort(source.url)
        token = _reddit_bearer_token(self._token_opener) if parsed else None
        if not parsed or token is None:
            return self._rss_fallback.fetch(source)
        sub, sort = parsed
        url = (f"https://oauth.reddit.com/r/{sub}/{sort}"
              f"?limit={self._max_items}&raw_json=1")
        raw, err = _read_bearer(self._opener, url, self._timeout, token, source=source)
        if raw is None:
            _report(self._on_outcome, source, False, err)
            return []
        try:
            children = _json.loads(raw)["data"]["children"]
        except Exception:  # noqa: BLE001
            _report(self._on_outcome, source, False, "unparseable reddit json")
            return []
        out: list[Item] = []
        for child in children[: self._max_items]:
            d = child.get("data", {}) if isinstance(child, dict) else {}
            ident = d.get("name") or d.get("id") or ""
            title = d.get("title", "")
            permalink = d.get("permalink", "")
            link_url = d.get("url", "")
            url_out = link_url if link_url.startswith("http") else (
                f"https://www.reddit.com{permalink}" if permalink else "")
            if ident:
                out.append(Item(id=ident, text=title or ident, url=url_out))
        _report(self._on_outcome, source, True, f"{len(out)} item(s)")
        return out


_ROBOTS_CACHE: dict[str, bool] = {}
_ROBOTS_LOCK = _threading.Lock()


def _robots_allow(url: str, opener: Callable | None = None,
                  deadline: float = 1.5) -> bool:
    """crawlee-hand-port-d: check robots.txt before crawling a new host
    for the first time (cached per host, like `_HOST_LAST`) — crawlee's
    default behavior, hand-ported. Fails OPEN on any error (unreachable
    robots.txt, timeout, parse failure) — a broken check must never
    strand a source that was working fine before.

    Runs the actual attempt in a background thread and bounds the CALLER's
    wait with `join(timeout=deadline)` rather than relying on urlopen's own
    `timeout=` kwarg — DNS resolution itself can hang well past that on a
    broken resolver/no route, a known stdlib gap `timeout=` doesn't cover.
    A slow/stuck attempt still fails open immediately; the orphaned daemon
    thread finishes (or doesn't) in the background, harmlessly, and caches
    the real answer for next time if it ever completes."""
    try:
        parsed = _urlparse(url)
        host = parsed.netloc.lower()
    except Exception:  # noqa: BLE001
        return True
    if not host:
        return True
    with _ROBOTS_LOCK:
        if host in _ROBOTS_CACHE:
            return _ROBOTS_CACHE[host]

    outcome: dict = {}

    def _work() -> None:
        allowed = True
        try:
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            ua = _pick_ua()
            op = opener
            if op is None:  # pragma: no cover — tests inject
                from urllib.request import Request, urlopen

                def op(u, timeout):  # type: ignore[misc]
                    return urlopen(Request(u, headers={"User-Agent": ua}),
                                  timeout=timeout)
            with op(robots_url, timeout=deadline) as resp:  # type: ignore[misc]
                text = resp.read().decode("utf-8", errors="ignore")
            import urllib.robotparser as _robotparser
            rp = _robotparser.RobotFileParser()
            rp.parse(text.splitlines())
            allowed = rp.can_fetch(ua, url)
        except Exception:  # noqa: BLE001 — fail open, never strand a source
            allowed = True
        outcome["allowed"] = allowed
        with _ROBOTS_LOCK:
            _ROBOTS_CACHE[host] = allowed

    worker = _threading.Thread(target=_work, daemon=True)
    worker.start()
    worker.join(timeout=deadline)
    return outcome.get("allowed", True)     # still stuck → fail open, now


class ChangeFetcher:
    """Emit one Item keyed on the content hash — dedup turns this into a
    change detector for free (restock pages, status pages, price pages)."""

    def __init__(self, opener: Callable | None = None, timeout: float = 10.0,
                 on_outcome: Callable | None = None,
                 robots_opener: Callable | None = None) -> None:
        self._opener = opener
        self._timeout = timeout
        self._on_outcome = on_outcome
        self._robots_opener = robots_opener

    def fetch(self, source: Source) -> list[Item]:
        if not _robots_allow(source.url, self._robots_opener):
            _report(self._on_outcome, source, False, "disallowed by robots.txt")
            return []
        raw, err = _read(self._opener, source.url, self._timeout, source=source)
        if raw is None:
            _report(self._on_outcome, source, False, err)
            return []
        _report(self._on_outcome, source, True, f"{len(raw)} bytes")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return [Item(id=digest, text=f"{source.name} changed (#{digest})")]


# retailer-scrape-d (Kevin, 2026-07-27): "I tried official APIs but
# decided to try our own scraping" — direct browser-based fetching for
# retail sites with no reliable RSS/API lane (Target, Best Buy, Pokémon
# Center). Sites register their own extractor by hostname (written
# against each site's REAL page structure); an unregistered host falls
# back to whole-page change detection (ChangeFetcher's own trick) so a
# scrape source is still useful — "this page changed" — before its real
# per-product parser exists.
_SCRAPE_PARSERS: dict[str, Callable] = {}


def register_scrape_parser(host: str, parser: Callable) -> None:
    """`parser(html: str, url: str) -> list[Item]`, registered by
    hostname (case-insensitive)."""
    _SCRAPE_PARSERS[host.lower()] = parser


def _default_scrape_parser(html: str, url: str) -> list[Item]:
    digest = hashlib.sha256((html or "").encode("utf-8", errors="ignore")).hexdigest()[:16]
    return [Item(id=digest, text=f"{url} changed (#{digest})", url=url)]


def _extract_apollo_ssr_blobs(html: str) -> list[dict]:
    """Best Buy's search pages embed their real product data as Apollo
    GraphQL SSR-hydration payloads: repeated
    `(window[Symbol.for("ApolloSSRDataTransport")] ??= []).push({...})`
    calls, each carrying a `rehydrate` cache fragment — live-verified
    against a real captured page (2026-07-27). Brace-matched (not regex
    non-greedy — these blobs nest real `{}` inside strings) since a naive
    regex silently truncates at the first inner `}`. `undefined` isn't
    valid JSON, so it's sanitized to `null` before parsing — the only
    transform applied; nothing else about the payload is altered."""
    marker = 'ApolloSSRDataTransport")] ??= []).push('
    blobs: list[dict] = []
    start = 0
    while True:
        idx = html.find(marker, start)
        if idx == -1:
            break
        brace_start = html.find("{", idx)
        if brace_start == -1:
            break
        depth, in_str, esc, end = 0, False, False, None
        i = brace_start
        while i < len(html):
            c = html[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            i += 1
        if end is None:
            break
        raw = html[brace_start:end + 1]
        try:
            obj = _json.loads(_re.sub(r':\s*undefined\b', ': null', raw))
            blobs.append(obj)
        except Exception:  # noqa: BLE001 — one bad blob never sinks the rest
            pass
        start = end + 1
    return blobs


def _parse_bestbuy(html: str, url: str) -> list[Item]:
    """Best Buy search-page parser — live-verified against a real
    captured page (2026-07-27): `documents[].product` carries `skuId`,
    `url.pdp` (the real product page), `productVariationListDisplay.
    title` (the name), and `price.customerPrice`/`displayableRegularPrice`
    (current vs. regular price — a real sale is visible directly).
    Falls back to the whole-page hash if the structure isn't found (a
    site redesign shouldn't silently stop posting, just get less
    specific) — never raises."""
    try:
        merged: dict = {}
        for blob in _extract_apollo_ssr_blobs(html):
            merged.update((blob.get("rehydrate") or {}))
        documents = []
        for entry in merged.values():
            data = entry.get("data") if isinstance(entry, dict) else None
            dps = data.get("detailedProductSearch") if isinstance(data, dict) else None
            if isinstance(dps, dict) and dps.get("documents"):
                documents = dps["documents"]
                break
        items: list[Item] = []
        for doc in documents:
            product = (doc or {}).get("product") or {}
            sku = product.get("skuId", "")
            title = (((product.get("name") or {}).get("title", "")) or
                    ((product.get("productVariationListDisplay") or {})
                     .get("title", "")) or "Unknown item")
            price = product.get("price") or {}
            current = price.get("customerPrice")
            regular = price.get("displayableRegularPrice")
            link = (product.get("url") or {}).get("pdp", url)
            if not sku:
                continue
            price_text = f"${current}" if current is not None else "price unknown"
            if regular is not None and current is not None and regular > current:
                price_text += f" (was ${regular})"
            items.append(Item(id=sku, text=f"{title} — {price_text}", url=link))
        if items:
            return items
    except Exception:  # noqa: BLE001 — a parse failure falls back, never crashes
        pass
    return _default_scrape_parser(html, url)


register_scrape_parser("www.bestbuy.com", _parse_bestbuy)


# target-parser-d (Kevin, 2026-07-27): live-reverified after the earlier
# captcha finding — target.com's product API (redsky_aggregations) is
# still captcha-walled, but the SEARCH PAGE itself (what a browser
# actually renders) came through clean this time, real product cards
# server-rendered directly into the HTML — no JSON blob needed at all,
# unlike Best Buy. Genuinely intermittent (a repeat attempt in the same
# session got a synthetic timeout, a later one succeeded) — same
# best-effort honesty as Pokémon Center/Costco; this parser only ever
# fires when the real markup is actually present, and falls back
# honestly otherwise.
_TGT_CARD_SPLIT = 'data-test="@web/site-top-of-funnel/ProductCardWrapper"'
_TGT_HREF_RE = _re.compile(r'<a[^>]+href="(/p/[^"]+/-/A-(\d+)[^"]*)"')
_TGT_TITLE_RE = _re.compile(
    r'data-test="@web/ProductCard/title"[^>]*href="[^"]*"><div[^>]+'
    r'title="([^"]+)"')
_TGT_PRICE_RE = _re.compile(r'data-test="current-price"><span>\$([\d.]+)</span>')
_TGT_WAS_RE = _re.compile(r'data-test="comparison-price">was <span[^>]*>\$([\d.]+)')


def _parse_target(html: str, url: str) -> list[Item]:
    """Target search-page parser — live-verified against a real captured
    page (2026-07-27, zip 42240): each product card is delimited by
    `data-test="@web/site-top-of-funnel/ProductCardWrapper"`, carrying a
    real `/p/<slug>/-/A-<tcin>` link (the tcin IS the stable item id),
    `data-test="@web/ProductCard/title"`'s `title="..."` attribute (the
    clean name, HTML-entity decoded), and `data-test="current-price"`/
    `"comparison-price"` (current vs. "was" price — a real sale is
    visible directly). Not every card matches (sponsored/bundle
    placements use a different shape) — those are silently skipped, not
    an error. Falls back to the whole-page hash if NO card matches at
    all (a redesign, or the captcha wall came through this time) — never
    raises."""
    import html as _html_mod
    try:
        items: list[Item] = []
        for chunk in html.split(_TGT_CARD_SPLIT)[1:]:
            chunk = chunk[:6000]      # bound the scan window per card
            m_href = _TGT_HREF_RE.search(chunk)
            if not m_href:
                continue
            tcin = m_href.group(2)
            link = "https://www.target.com" + m_href.group(1).split("#")[0]
            m_title = _TGT_TITLE_RE.search(chunk)
            title = (_html_mod.unescape(m_title.group(1)) if m_title
                    else "Unknown item")
            m_price = _TGT_PRICE_RE.search(chunk)
            price = m_price.group(1) if m_price else ""
            m_was = _TGT_WAS_RE.search(chunk)
            was = m_was.group(1) if m_was else ""
            price_text = f"${price}" if price else "price unknown"
            if was and was != price:
                price_text += f" (was ${was})"
            items.append(Item(id=tcin, text=f"{title} — {price_text}", url=link))
        if items:
            return items
    except Exception:  # noqa: BLE001 — a parse failure falls back, never crashes
        pass
    return _default_scrape_parser(html, url)


register_scrape_parser("www.target.com", _parse_target)


# dollargeneral-parser-d (Kevin, 2026-07-27): "add a dollar general
# category for pokemon" — live-verified (2026-07-27): the real search
# endpoint is `/product-search?q=<term>` (a bare `/search?q=` 404s —
# checked the homepage's own search form action to find the real path).
# Server-rendered product tiles, clean and consistent (2/2 cards matched
# on the first real capture) — no JSON blob needed, same shape as
# Target's cards. Kevin separately noted DG's site has an in-store-stock
# feature; not confirmed present on the anonymous search-results page
# itself (no zip/store context set) — same honest limit as
# store_mentions.py's per-store seam, not fabricated here.
_DG_CARD_SPLIT = 'product-tile-wrapper"'
_DG_HREF_RE = _re.compile(r'<a class="product-card__navigation" href="(/p/[^"]+/(\d+))"')
_DG_TITLE_RE = _re.compile(r'class="product--title">([^<]+)</a>')
_DG_PRICE_RE = _re.compile(
    r'class="product-price product-card__current-price">\$([\d.]+)</span>')


def _parse_dollargeneral(html: str, url: str) -> list[Item]:
    """DollarGeneral.com search-page parser — live-verified against a
    real captured page (2026-07-27, "pokemon"): each product tile is
    delimited by `product-tile-wrapper"`, carrying a real
    `/p/<slug>/<upc>` link (the UPC is the stable item id),
    `class="product--title"` (the clean name), and
    `class="...product-card__current-price"` (the price). Falls back to
    the whole-page hash if no tile matches at all — never raises."""
    import html as _html_mod
    try:
        items: list[Item] = []
        for chunk in html.split(_DG_CARD_SPLIT)[1:]:
            chunk = chunk[:4000]      # bound the scan window per card
            m_href = _DG_HREF_RE.search(chunk)
            if not m_href:
                continue
            upc = m_href.group(2)
            link = "https://www.dollargeneral.com" + m_href.group(1)
            m_title = _DG_TITLE_RE.search(chunk)
            title = (_html_mod.unescape(m_title.group(1)).strip() if m_title
                    else "Unknown item")
            m_price = _DG_PRICE_RE.search(chunk)
            price_text = f"${m_price.group(1)}" if m_price else "price unknown"
            items.append(Item(id=upc, text=f"{title} — {price_text}", url=link))
        if items:
            return items
    except Exception:  # noqa: BLE001 — a parse failure falls back, never crashes
        pass
    return _default_scrape_parser(html, url)


register_scrape_parser("www.dollargeneral.com", _parse_dollargeneral)

# county-records-d (Kevin, 2026-08-01): "county public records for
# christian county and montgomery county" -- real, verified-live
# court-listing pages (foreclosure/tax-sale), not guessed. Reddit
# ruled out (Kevin's account is banned).
def _parse_christian_county_ky(html: str, url: str) -> list[Item]:
    from sovereign_agent.real_estate_county_records import fetch_christian_county_items
    return fetch_christian_county_items(html, url)
register_scrape_parser("christiancountymastercommissioner.com", _parse_christian_county_ky)

def _parse_montgomery_county_tn(html: str, url: str) -> list[Item]:
    from sovereign_agent.real_estate_county_records import fetch_montgomery_county_items
    return fetch_montgomery_county_items(html, url)
register_scrape_parser("montgomerytn.gov", _parse_montgomery_county_tn)

# lien-auction-d (Kevin, 2026-08-01): "add liens in the real estate
# section for title auctions" -- Christian County KY delinquent
# property tax sale date/registration deadline, verified live.
# Weekly seasonal check per Kevin's own choice, not continuous.
def _parse_christian_county_tax_sale(html: str, url: str) -> list[Item]:
    from sovereign_agent.real_estate_lien_auctions import fetch_christian_county_tax_sale_items
    return fetch_christian_county_tax_sale_items(html, url)
register_scrape_parser("christiancountyky.gov", _parse_christian_county_tax_sale)

# edmonson-county-d (Kevin, 2026-08-01): "extend the real estate
# radar to a few good and active real estate communities" --
# Edmonson County KY (Brownsville), confirmed real + server-
# rendered (curled directly), a 3rd source for single-family.
def _parse_edmonson_county_ky(html: str, url: str) -> list[Item]:
    from sovereign_agent.real_estate_edmonson_county import fetch_edmonson_county_items
    return fetch_edmonson_county_items(html, url)
register_scrape_parser("www.edmonsoncountymastercommissioner.com", _parse_edmonson_county_ky)


class ScrapeFetcher:
    """Browser-based fetch via the hardened stealth session
    (`stealth_browser.py`) — for direct retailer sites with no reliable
    RSS/API lane. Reuses the SAME per-host cooldown mechanism as every
    other fetcher here: a detected block (`stealth_browser.looks_blocked`)
    backs off exactly like a real 429, never hammered. `session` is
    injectable for tests (an object with `.visit(url) -> (html, status)`);
    when None, uses the process-wide shared `StealthSession`, serialized
    via `scrape_lock()` (a background duty loop must never pile up
    concurrent headless-Chromium instances)."""

    def __init__(self, session=None, on_outcome: Callable | None = None) -> None:
        self._session = session
        self._on_outcome = on_outcome

    def fetch(self, source: Source) -> list[Item]:
        cooldown = _cooldown_remaining(source.url)
        if cooldown > 0:
            _report(self._on_outcome, source, False,
                   f"backing off {cooldown:.0f}s after repeated blocks")
            return []
        from .stealth_browser import get_shared_session, looks_blocked, scrape_lock
        session = self._session if self._session is not None else get_shared_session()
        with scrape_lock():
            html, status = session.visit(source.url)
        if looks_blocked(html, status):
            _note_outcome(source.url, False, 429)
            _report(self._on_outcome, source, False, f"blocked (status {status})")
            return []
        _note_outcome(source.url, True, None)
        try:
            host = _urlparse(source.url).netloc.lower()
        except Exception:  # noqa: BLE001
            host = ""
        parser = _SCRAPE_PARSERS.get(host, _default_scrape_parser)
        items = parser(html, source.url)
        _report(self._on_outcome, source, True, f"{len(items)} item(s)")
        return items


_WF_API = "https://api.warframe.market/v2"
_WF_API_V1 = "https://api.warframe.market/v1"
_WF_CACHE_MAX_AGE_S = 86400.0    # refresh the item pools at most once/day
# opportunity-volume-d (Kevin, 2026-07-27): "I want the warframe channels
# to be blowing up with opportunities." Real constraint, not a knob to
# ignore: every scan is a real, politely-paced HTTP call (_throttle,
# 0.4s/request, shared across ALL warframe channels since they hit the
# same host) inside `mgr.tick()`'s SYNCHRONOUS sweep of every tracker in
# the bot — a too-large batch blocks the whole duty loop (mail replies,
# live-ping DMs, every other tracker) for that long, not just Warframe.
# 10→15 (was the default since this all started): relics (the biggest,
# slowest-sweeping pool, ~729 items) goes from a ~73min full sweep to
# ~49min; sets/arcanes/riven sweep meaningfully faster too. More items
# scanned per tick = more of the REAL market actually checked, not a
# lowered bar for what counts as a flip.
_WF_BATCH_SIZE = 15              # sets/relics/arcanes/rivens scanned per tick


def _wf_cache_path(data_dir):
    from pathlib import Path
    return Path(data_dir) / "warframe_market" / "cache.json"


def _wf_load_cache(data_dir) -> dict:
    try:
        return _json.loads(_wf_cache_path(data_dir).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _wf_save_cache(data_dir, cache: dict) -> None:
    path = _wf_cache_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(_json.dumps(cache), encoding="utf-8")
    tmp.replace(path)


def _wf_get(opener: Callable | None, url: str, timeout: float = 10.0):
    """A GET returning parsed JSON — warframe.market's payload shape is
    entirely its own, so this stays separate from `_read` (which returns
    raw bytes for the RSS/JSON/change fetchers). Same throttle/backoff
    bookkeeping as every other fetcher in this module."""
    _throttle(url)
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, timeout):  # type: ignore[misc]
            req = Request(u, headers={"Platform": "pc", "User-Agent": _pick_ua()})
            return urlopen(req, timeout=timeout)
    try:
        with opener(url, timeout=timeout) as resp:  # type: ignore[misc]
            data = resp.read()
        _note_outcome(url, True, None)
        return _json.loads(data)
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        _note_outcome(url, False, code)
        raise


def _wf_refresh_pools(opener: Callable | None) -> dict:
    """Real API calls — the full item catalog + riven weapon list.
    Called at most once/day (see `_WF_CACHE_MAX_AGE_S`); everything else
    (orders/auctions per item) happens per-tick in small rotating
    batches, never here."""
    items = _wf_get(opener, f"{_WF_API}/items").get("data", [])
    sets, relics, arcanes, misc, id_to_slug = [], [], [], [], {}
    # middleman-lookup-d (Kevin, 2026-07-27): "type in items I want to
    # sell... like a middle man loop up wizard" — the lookup command
    # needs to search across EVERY real tradeable item, not just the
    # curated sets/relics/arcanes/misc pools above (those are deliberately
    # narrow scans; a lookup is on-demand and should find anything).
    all_items = [{"slug": it.get("slug", ""),
                 "name": ((it.get("i18n") or {}).get("en") or {}).get("name", "")}
                for it in items if it.get("slug") and
                ((it.get("i18n") or {}).get("en") or {}).get("name")]
    # vaulted-relics-d (Kevin, 2026-07-27): the real "<Name> Prime"
    # base names, from sets SPECIFICALLY tagged "warframe" (live-
    # verified: weapon Prime sets are tagged "weapon" instead — e.g.
    # "Vasto Prime Set" carries no "warframe" tag) — needed to tell a
    # Warframe part apart from a weapon part sharing the same "...
    # Blueprint" suffix in a relic's reward list.
    warframe_names: list[str] = []
    for it in items:
        slug = it.get("slug", "")
        id_to_slug[it.get("id", "")] = slug
        tags = [t.lower() for t in (it.get("tags") or [])]
        name = ((it.get("i18n") or {}).get("en") or {}).get("name", slug)
        if "set" in tags and "prime" in tags:
            sets.append({"slug": slug, "name": name})
            if "warframe" in tags:
                warframe_names.append(name[:-4] if name.endswith(" Set") else name)
        elif "relic" in tags and it.get("vaulted"):
            # retailer-scrape-d precedent applied here too: "rare
            # relics" (Kevin's words) = vaulted, not the full 772-item
            # catalog scanned at equal priority.
            relics.append({"slug": slug, "name": name})
        elif "arcane_enhancement" in tags:
            arcanes.append({"slug": slug, "name": name})
        elif "fusion core" in tags:
            # warframe-misc-d (Kevin, 2026-07-27): "add legendary core
            # flips too or a miscellaneous category" — live-verified,
            # only 2 real items carry this tag (Legendary + Ancient
            # Fusion Core), both single fungible SKUs with real order
            # books, same shape as a Prime Set (no rank/subtype variant
            # needed). A real, extensible bucket, not hardcoded to one
            # item — the NEXT genuinely tradeable single-item find just
            # needs a tag match added here, never a fabricated list.
            misc.append({"slug": slug, "name": name})
    weapons = _wf_get(opener, f"{_WF_API}/riven/weapons").get("data", [])
    riven_weapons = [
        {"slug": w["slug"],
         "name": ((w.get("i18n") or {}).get("en") or {}).get("name", w["slug"]),
         "disposition": float(w.get("disposition", 1.0) or 1.0)}
        for w in weapons if w.get("disposition")]
    riven_weapons.sort(key=lambda w: -w["disposition"])  # highest-disposition first
    return {"sets": sets, "relics": relics, "arcanes": arcanes, "misc": misc,
           "riven_weapons": riven_weapons[:40], "id_to_slug": id_to_slug,
           "all_items": all_items, "warframe_names": warframe_names}


def wf_item_search(cache: dict, query: str, limit: int = 25) -> list[dict]:
    """middleman-lookup-d (Kevin, 2026-07-27): case-insensitive substring
    search over the cached full item catalog — "type in items I want to
    sell. Or I can select items from a drop down." This is the "type"
    half; a prefix match ranks above a mid-string match, shorter names
    (closer matches) break ties. Empty query -> no results, never a
    random dump."""
    q = (query or "").strip().lower()
    if not q:
        return []
    hits = [it for it in cache.get("all_items", []) if q in it["name"].lower()]
    hits.sort(key=lambda it: (not it["name"].lower().startswith(q), len(it["name"])))
    return hits[:limit]


def wf_lookup_item(opener: Callable | None, slug: str, name: str) -> list:
    """middleman-lookup-d: the real, live half — fetches this ONE item's
    real orders and ranks its real buyers, highest profit first (see
    `warframe_market.lookup_opportunities`). No pool/cache involved —
    a lookup is on-demand and always wants the current picture."""
    from sovereign_agent import warframe_market as wfm
    raw = _wf_get(opener, f"{_WF_API}/orders/item/{slug}")
    orders = wfm.parse_orders(raw.get("data") or [],
                              variant_of=lambda o: o.get("subtype") or o.get("rank") or "")
    return wfm.lookup_opportunities(name, orders)


# vaulted-relics-d (Kevin, 2026-07-27): "Add a vaulted relics command
# that shows all of the active warframe vaulted relics/warframes...
# What relics go to what part of the warframe." Cross-references
# warframe.market's real `vaulted` relic flag against the real
# community drop table (drops.warframestat.us, WFCD — same trust tier
# as warframe.market for third-party tools) — see warframe_vault.py's
# module docstring for why NEITHER source alone can answer this.
_WF_DROPS_URL = "https://drops.warframestat.us/data/relics.json"
_WF_DROPS_CACHE_MAX_AGE_S = 3 * 86400.0  # drop tables change rarely — 3 days is generous


def _wf_relic_ref_from_name(name: str) -> tuple[str, str] | None:
    """"Axi H3 Relic" -> ("Axi", "H3"). None if the shape's unexpected —
    never a guess."""
    if name.endswith(" Relic"):
        name = name[: -len(" Relic")]
    parts = name.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None


def _wf_drops_cache_path(data_dir):
    from pathlib import Path
    return Path(data_dir) / "warframe_market" / "drops_cache.json"


def _wf_load_drops_cache(data_dir) -> dict:
    try:
        return _json.loads(_wf_drops_cache_path(data_dir).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _wf_save_drops_cache(data_dir, cache: dict) -> None:
    path = _wf_drops_cache_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(cache), encoding="utf-8")
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def _wf_relic_rewards(opener: Callable | None, data_dir) -> dict[tuple[str, str], list[str]]:
    """{(tier, relicName): [reward itemName, ...]} from the real
    community drop table — cached (drop tables change rarely, unlike
    per-item market orders) so a lookup doesn't re-fetch a ~3000-entry
    payload every time. Only "Intact" state kept: the same items drop
    at every refinement, just at different odds — the other 3 states
    would only duplicate the part→relic mapping, never change it."""
    now = _time.time()
    cache = _wf_load_drops_cache(data_dir)
    if (now - float(cache.get("fetched_at", 0)) <= _WF_DROPS_CACHE_MAX_AGE_S
            and cache.get("rewards")):
        return {tuple(k.split("\x00")): v for k, v in cache["rewards"].items()}
    raw = _wf_get(opener, _WF_DROPS_URL)
    rewards: dict[tuple[str, str], list[str]] = {}
    for r in raw.get("relics", []) or []:
        if r.get("state") != "Intact":
            continue
        key = (r.get("tier", ""), r.get("relicName", ""))
        rewards[key] = [x.get("itemName", "") for x in (r.get("rewards") or [])]
    _wf_save_drops_cache(data_dir, {
        "fetched_at": now,
        "rewards": {"\x00".join(k): v for k, v in rewards.items()},
    })
    return rewards


def wf_vault_map(opener: Callable | None, data_dir) -> dict:
    """The full, real {warframe_name: {part: [RelicRef, ...]}} map —
    see warframe_vault.build_vault_map for the pure cross-reference
    logic this wraps with real I/O (the same WFM pool cache the flip
    fetcher already maintains, plus the drop-table cache above)."""
    from sovereign_agent import warframe_vault as wv
    cache = _wf_load_cache(data_dir)
    now = _time.time()
    if (now - float(cache.get("fetched_at", 0)) > _WF_CACHE_MAX_AGE_S
            or not cache.get("warframe_names")):
        try:
            fresh = _wf_refresh_pools(opener)
        except Exception:  # noqa: BLE001
            if not cache.get("warframe_names"):
                return {}
        else:
            fresh["fetched_at"] = now
            fresh["cursors"] = cache.get("cursors", {})
            cache = fresh
            _wf_save_cache(data_dir, cache)
    vaulted_relics = []
    for entry in cache.get("relics", []):
        ref = _wf_relic_ref_from_name(entry.get("name", ""))
        if ref:
            vaulted_relics.append(ref)
    rewards = _wf_relic_rewards(opener, data_dir)
    return wv.build_vault_map(vaulted_relics, rewards, cache.get("warframe_names", []))


# warframe-arcane-ranks-d (Kevin, 2026-07-27): "rank 0 flips, mid
# flips, and rank 5 flips" — three category markers sharing the SAME
# "arcanes" item pool (the fetcher's rotation cursor is still per-marker,
# so each channel independently sweeps the whole catalog on its own
# schedule); the rank scope is applied to each item's ORDERS in
# `_scan_one`, not to which items get picked. Empty variant ("") folds
# into rank 0 — same treatment the daily market-texture report already
# gives an arcane with no explicit rank on an order.
_WF_ARCANE_RANK_SCOPES = {
    "arcane-rank0": {"0", ""},
    "arcane-mid": {"1", "2", "3", "4"},
    "arcane-rank5": {"5"},
    # jackpot-d (Kevin, 2026-07-27): internal-only scope used by the
    # jackpot scan below — every rank in ONE pass (never exposed as its
    # own channel/vertical; `_group_by_variant` already keeps ranks from
    # ever being compared against each other within a single scan).
    "arcane-all": {"0", "1", "2", "3", "4", "5", ""},
}
_WF_CATEGORY_POOL_KEY = {"set": "sets", "relic": "relics",
                        "arcane-rank0": "arcanes", "arcane-mid": "arcanes",
                        "arcane-rank5": "arcanes", "riven": "riven_weapons",
                        "misc": "misc",
                        # jackpot-d: not a real cache key — its pool is
                        # built specially (combined across every other
                        # pool) right where this dict is consulted; it's
                        # only listed here so the category-validation
                        # check below accepts it.
                        "jackpot": "jackpot"}

_WF_JACKPOT_MIN_PROFIT = 150     # platinum — the absolute floor
_WF_JACKPOT_MIN_RATIO = 2.0      # sell >= 2x buy — the multiplier floor


def _is_jackpot(opp) -> bool:
    """opportunities-of-a-lifetime-d (Kevin, 2026-07-27): "some crazy
    deal or opportunity... one in a lifetime chance." "Make it hyper
    intelligent and harden the system" — multiple confirming signals,
    not one fragile threshold: must be a REAL, immediately-executable
    quick flip (a confirmed live buyer — never an estimate) AND clear
    BOTH a high absolute profit floor and a strong profit ratio. Either
    alone lets noise through: a big-ticket item's modest percentage
    margin clears the ratio-less absolute floor; a cheap item's huge
    multiplier clears the profit-less ratio floor. Both together is
    what actually earns "opportunity of a lifetime," not "a decent flip.\""""
    if not opp.sell_targets or opp.buy_platinum <= 0:
        return False
    ratio = opp.sell_platinum / opp.buy_platinum
    return (opp.profit >= _WF_JACKPOT_MIN_PROFIT
           and ratio >= _WF_JACKPOT_MIN_RATIO)


def _wf_jackpot_pool(cache: dict) -> list[tuple[str, dict]]:
    """jackpot-d: one combined sweep across EVERY item type — sets,
    relics, arcanes (all ranks in one pass), riven weapons, misc —
    tagged with each entry's REAL sub-category so `_scan_one` dispatches
    exactly as it would from that item's own channel; only the
    `_is_jackpot` filter downstream is jackpot-specific."""
    return ([("set", e) for e in cache.get("sets", [])]
           + [("relic", e) for e in cache.get("relics", [])]
           + [("arcane-all", e) for e in cache.get("arcanes", [])]
           + [("riven", e) for e in cache.get("riven_weapons", [])]
           + [("misc", e) for e in cache.get("misc", [])])


class WarframeFlipFetcher:
    """Warframe Market flip-finder (warframe-flip-d, Kevin 2026-07-27):
    "add a warframe market scraper that is intelligent. Finding us items
    we can flip." — then, on seeing it land as one lumped channel:
    "Well I wanted a whole warframe category, with channels for item
    types." Each `Source` now scans exactly ONE category (`source.url`
    carries which: "set" | "relic" | "arcane-rank0" | "arcane-mid" |
    "arcane-rank5" | "riven" — a marker, not a real URL, matching
    `scrape()`'s established convention of repurposing
    `url` for non-HTTP fetchers), so each item type gets its OWN channel
    and its OWN independent rotation through the real, official, no-auth
    warframe.market API. Logic lives in `warframe_market.py`; this is the
    I/O wrapper (shared cache refresh across all four categories, one
    real HTTP call's worth of politeness, per-category rotation)."""

    def __init__(self, opener: Callable | None = None,
                 on_outcome: Callable | None = None, data_dir=None,
                 batch_size: int = _WF_BATCH_SIZE) -> None:
        self._opener = opener
        self._on_outcome = on_outcome
        self._data_dir = data_dir
        self._batch_size = batch_size

    def _resolve_data_dir(self):
        if self._data_dir is not None:
            return self._data_dir
        from sovereign_agent.config import SETTINGS
        return SETTINGS.paths.data_dir

    def fetch(self, source: Source) -> list[Item]:
        cooldown = _cooldown_remaining(f"{_WF_API}/")
        if cooldown > 0:
            _report(self._on_outcome, source, False,
                   f"backing off {cooldown:.0f}s after repeated 429/503")
            return []
        category = (source.url or "").strip().lower()
        if category not in _WF_CATEGORY_POOL_KEY:
            _report(self._on_outcome, source, False,
                   f"unknown warframe category {category!r} (source.url)")
            return []
        data_dir = self._resolve_data_dir()
        cache = _wf_load_cache(data_dir)
        now = _time.time()
        if now - float(cache.get("fetched_at", 0)) > _WF_CACHE_MAX_AGE_S or not cache.get("sets"):
            try:
                fresh = _wf_refresh_pools(self._opener)
            except Exception as exc:  # noqa: BLE001
                _report(self._on_outcome, source, False,
                       f"pool refresh failed: {type(exc).__name__}")
                if not cache.get("sets"):
                    return []          # nothing cached yet — nothing to scan this tick
            else:
                fresh["fetched_at"] = now
                fresh["cursors"] = cache.get("cursors", {})
                cache = fresh

        if category == "jackpot":
            pool = _wf_jackpot_pool(cache)
        else:
            pool_key = _WF_CATEGORY_POOL_KEY[category]
            pool = [(category, e) for e in cache.get(pool_key, [])]
        if not pool:
            _wf_save_cache(data_dir, cache)
            return []
        cursors = cache.setdefault("cursors", {})
        cursor = int(cursors.get(category, 0)) % len(pool)
        batch = [pool[(cursor + i) % len(pool)] for i in range(min(self._batch_size, len(pool)))]
        cursors[category] = (cursor + len(batch)) % len(pool)
        _wf_save_cache(data_dir, cache)

        items: list[Item] = []
        for cat, entry in batch:
            try:
                hits = self._scan_one(cat, entry, cache)
            except Exception:  # noqa: BLE001 — one bad item never sinks the tick
                hits = []
            if category == "jackpot":
                hits = [h for h in hits if _is_jackpot(h)]
            jackpot = category == "jackpot"
            for opp in hits:
                key = f"{entry['slug']}:{opp.strategy}:{'-'.join(opp.order_ids)}"
                item_url = f"https://warframe.market/items/{entry['slug']}"
                items.append(Item(
                    id=key, text=self._format(opp, jackpot=jackpot), url=item_url,
                    embed=self._build_embed(opp, item_url, jackpot=jackpot)))
        _report(self._on_outcome, source, True,
               f"{len(items)} opportunity(ies) from a batch of {len(batch)}")
        return items

    def _scan_one(self, category: str, entry: dict, cache: dict):
        from sovereign_agent import warframe_market as wfm
        if category == "riven":
            raw = _wf_get(self._opener,
                          f"{_WF_API_V1}/auctions/search?type=riven"
                          f"&weapon_url_name={entry['slug']}")
            auctions = wfm.parse_riven_auctions(
                ((raw.get("payload") or {}).get("auctions")) or [])
            return wfm.riven_opportunities(
                entry["name"], auctions, disposition=entry.get("disposition", 1.0))
        raw = _wf_get(self._opener, f"{_WF_API}/orders/item/{entry['slug']}")
        variant_of = None
        if category == "relic" or category in _WF_ARCANE_RANK_SCOPES:
            def variant_of(o):  # noqa: E306
                return o.get("subtype") or o.get("rank") or ""
        orders = wfm.parse_orders(raw.get("data") or [], variant_of=variant_of)
        # warframe-arcane-ranks-d (Kevin, 2026-07-27): "I want rank 0
        # arcanes channel and a rank 5 arcanes channel... 3 channel.
        # Rank 0 flips, mid flips, and rank 5 flips" — three independent
        # scopes over the SAME arcane catalog, so cheap (rank 0) and
        # expensive (rank 5) never mix in one channel. Filtered here,
        # before the strategies run, so `_group_by_variant` inside them
        # never even sees the ranks this channel doesn't care about.
        if category in _WF_ARCANE_RANK_SCOPES:
            ranks = _WF_ARCANE_RANK_SCOPES[category]
            orders = [o for o in orders if o.variant in ranks]
        set_parts_orders = None
        if category == "set":
            set_parts_orders = self._parts_orders_for(entry, cache)
        return wfm.find_opportunities(entry["name"], orders, category=category,
                                      set_parts_orders=set_parts_orders)

    def _parts_orders_for(self, set_entry: dict, cache: dict) -> dict:
        from sovereign_agent import warframe_market as wfm
        detail = _wf_get(self._opener, f"{_WF_API}/item/{set_entry['slug']}").get("data") or {}
        part_ids = detail.get("setParts") or []
        id_to_slug = cache.get("id_to_slug") or {}
        out: dict = {}
        for pid in part_ids:
            slug = id_to_slug.get(pid)
            if not slug or slug == set_entry["slug"]:
                continue
            raw = _wf_get(self._opener, f"{_WF_API}/orders/item/{slug}")
            out[pid] = wfm.parse_orders(raw.get("data") or [])
        return out

    _CATEGORY_TAG = {"set": "Set", "relic": "Relic", "riven": "Riven", "misc": "Misc",
                    "arcane-rank0": "Arcane R0", "arcane-mid": "Arcane R1-4",
                    "arcane-rank5": "Arcane R5", "arcane-all": "Arcane"}
    _CATEGORY_COLOR = {"set": 0x1B9CFC, "relic": 0x9B59B6, "riven": 0xE74C3C,
                      "misc": 0xF1C40F, "arcane-rank0": 0x2ECC71,
                      "arcane-mid": 0x3498DB, "arcane-rank5": 0xE67E22,
                      "arcane-all": 0x9B59B6}
    _STATUS_ICON = {"ingame": "🟢", "online": "🟡", "offline": "⚪"}
    # flip-kind-d (Kevin, 2026-07-27): "everything else with active
    # buyers where we can make immediate profit should be posted and
    # labeled quick flips" + "label stuff [with] no active buyers
    # mid-long term flips" — nothing gets suppressed; a real active
    # buyer is what separates "sell it right now" from "list it and
    # wait," so the label is driven by that, not a guess.
    _QUICK_FLIP = "⚡ Quick Flip"
    _MIDLONG_FLIP = "📦 Mid/Long-Term Flip"

    _JACKPOT_MARK = "🎰 JACKPOT"
    _JACKPOT_COLOR = 0xFFD700   # gold — deliberately distinct from every category color

    @classmethod
    def _flip_kind(cls, opp) -> str:
        return cls._QUICK_FLIP if opp.sell_targets else cls._MIDLONG_FLIP

    @classmethod
    def _format(cls, opp, *, jackpot: bool = False) -> str:
        """The short line riding beside the rich embed (`_build_embed`) —
        Discord's `content`, shown above the embed card; kept brief since
        the embed carries the buy/sell/status detail now."""
        tag = cls._CATEGORY_TAG.get(opp.category, opp.category)
        prefix = f"{cls._JACKPOT_MARK} " if jackpot else ""
        return (f"{prefix}{cls._flip_kind(opp)} [{tag}] {opp.item_name} "
               f"— {opp.profit}p profit")

    @classmethod
    def _build_embed(cls, opp, item_url: str, *, jackpot: bool = False) -> dict:
        """panel-d (Kevin, 2026-07-27): "present the item to buy plus
        the best people to sell it to... make each post like an
        advanced panel where we can keep track of users activity (if
        they are ingame, or offline)." One embed per opportunity: who
        to buy from, up to 5 real live buyers ranked best-price-first
        (each labeled with their live status), and an honest fallback
        line — never a fabricated buyer — when none are visible.

        jackpot-d (Kevin, 2026-07-27): "opportunities of a lifetime" —
        `jackpot=True` marks a post that already cleared `_is_jackpot`'s
        hardened bar (real buyer + high absolute profit + high ratio) —
        a distinct gold color + "🎰 JACKPOT" prefix so it can never be
        mistaken for an ordinary Quick Flip at a glance."""
        from sovereign_agent.discord_limits import clamp_embed
        tag = cls._CATEGORY_TAG.get(opp.category, opp.category)
        color = cls._JACKPOT_COLOR if jackpot else cls._CATEGORY_COLOR.get(
            opp.category, 0x1B9CFC)
        fields = [
            {"name": "💰 Buy", "value": f"**{opp.buy_platinum}p** from {opp.buy_from}",
             "inline": True},
            {"name": "📈 Profit", "value": f"**{opp.profit}p**", "inline": True},
        ]
        if opp.sell_targets:
            lines = []
            for t in opp.sell_targets:
                icon = cls._STATUS_ICON.get(t.status, "⚪")
                lines.append(f"{icon} **{t.ingame_name}** — {t.platinum}p ({t.status})")
            plural = "s" if len(opp.sell_targets) != 1 else ""
            fields.append({
                "name": f"📤 Sell to ({len(opp.sell_targets)} live buyer{plural})",
                "value": "\n".join(lines), "inline": False})
        else:
            note = (f"~{opp.sell_platinum}p — peer-median estimate, no live "
                   "buyers right now" if opp.sell_is_estimate
                   else "no live buyers right now")
            fields.append({"name": "📤 Sell to",
                           "value": f"⚠ {note}", "inline": False})
        if opp.detail:
            fields.append({"name": "Detail", "value": opp.detail, "inline": False})
        prefix = f"{cls._JACKPOT_MARK} " if jackpot else ""
        return clamp_embed({
            "title": f"{prefix}{cls._flip_kind(opp)} [{tag}] {opp.item_name}",
            "url": item_url,
            "color": color,
            "fields": fields,
            "footer": {"text": "prices + status as of this post"},
        })


def fetcher_for(source: Source, opener: Callable | None = None,
                on_outcome: Callable | None = None):
    """Pick the right fetcher for a source's declared kind. `manual` and any
    unknown kind get the inert NullFetcher (safe default). `on_outcome`
    (source_name, ok, detail) feeds source-health telemetry (R5a)."""
    kind = (source.kind or "").lower()
    if kind == "rss":
        if _is_reddit_url(source.url):
            return RedditFetcher(opener=opener, on_outcome=on_outcome)
        return RssFetcher(opener=opener, on_outcome=on_outcome)
    if kind in ("api", "json"):
        return HttpJsonFetcher(opener=opener, on_outcome=on_outcome)
    if kind in ("http", "change", "page"):
        return ChangeFetcher(opener=opener, on_outcome=on_outcome)
    if kind == "warframe-flip":
        return WarframeFlipFetcher(opener=opener, on_outcome=on_outcome)
    if kind == "osrs-flip":
        # osrs-flips-d: official wiki price API, no auth, identifying UA.
        from sovereign_agent.osrs_flips.fetcher import OsrsFlipFetcher
        return OsrsFlipFetcher(opener=opener, on_outcome=on_outcome)
    if kind == "grants-gov":
        # income-securing-d (Kevin, 2026-08-01): a real, live,
        # no-auth federal grants API -- POSTs a JSON body, so it
        # needs its own Fetcher rather than HttpJsonFetcher (GET-only).
        from sovereign_agent.grants_tracker import GrantsGovFetcher
        return GrantsGovFetcher(opener=opener, on_outcome=on_outcome)
    if kind == "scrape":
        return ScrapeFetcher(on_outcome=on_outcome)
    return NullFetcher()
