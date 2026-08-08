"""api_providers.py — 🔑 the Key Concierge registry (Kevin's ask).

"Make gathering the proper API keys easy, simple, legitimate and safe."
The honesty line (her kernel): a program CAN'T auto-harvest API keys —
every provider needs a human to register + accept ToS, and auto-creating
accounts violates ToS. So this is a CONCIERGE: it makes KEVIN's path
frictionless (exact link, steps, least-privilege scope), validates the
key live, and vaults it safely. Where data is genuinely keyless/public
(weather, deal RSS), she already uses it directly — nothing to gather.

Each Provider knows what it UNLOCKS (which scout feature), so the status
view answers "what do I need for per-store Target stock?" honestly.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    slug: str                       # sov keys onboard <slug>
    name: str                       # display name
    unlocks: str                    # the scout feature this turns on
    env_vars: list[str]             # vault key(s) it fills
    signup_url: str                 # the direct link to start
    steps: list[str]                # numbered, click-by-click
    free: bool = True               # free tier available?
    time_note: str = "~5 min"       # how long it takes
    scope: str = ""                 # least-privilege scope to request
    probe: str = ""                 # credentials.probe_<name> to validate
    tos_note: str = ""              # the legitimacy note
    keyless_alt: str = ""           # what public source covers this today
    keyless: bool = False           # True = no key needed, already working


PROVIDERS: list[Provider] = [
    Provider(
        slug="reddit",
        name="Reddit API (official)",
        unlocks="Higher rate limits for the deal/restock trackers — ends "
                "the HTTP 429 throttling we hit polling many niches; more "
                "legitimate than public RSS.",
        env_vars=["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
        signup_url="https://www.reddit.com/prefs/apps",
        steps=[
            "Log in to Reddit, open https://www.reddit.com/prefs/apps",
            "Scroll down → 'are you a developer? create an app…'",
            "Name: BigKevsBotShop-Scout · type: **script**",
            "redirect uri: http://localhost:8080 (unused, but required)",
            "Create app. The string under the app name is your CLIENT ID; "
            "'secret' is your CLIENT SECRET",
            "Vault both: sov keys onboard reddit (paste id, then secret)",
        ],
        free=True, time_note="~5 min, instant",
        scope="read-only (a 'script' app needs no special scopes)",
        probe="probe_reddit",
        tos_note="Official Reddit API — free tier, ToS-compliant. Identify "
                 "with a descriptive User-Agent (we do).",
        keyless_alt="Reddit RSS (dead in practice — the anonymous endpoint "
                    "is rate-limited to zero throughput fleet-wide, not "
                    "just 'under load'; this key is the real fix, not an "
                    "optional upgrade)."),
    Provider(
        slug="bestbuy",
        name="Best Buy Developer API",
        unlocks="REAL product availability + PER-STORE stock — the true "
                "local lane (is it in stock at YOUR store, pickup vs ship).",
        env_vars=["BESTBUY_API_KEY"],
        signup_url="https://developer.bestbuy.com/",
        steps=[
            "Open https://developer.bestbuy.com/ → 'Get API Key'",
            "Sign up (email + basic info), confirm your email",
            "Your API key appears on the dashboard immediately",
            "Vault it: sov keys onboard bestbuy",
        ],
        free=True, time_note="~5-10 min, instant key",
        scope="Products + Stores (read-only — the default)",
        probe="probe_bestbuy",
        tos_note="Official Best Buy developer program — free, ToS-compliant. "
                 "Rate-limited (5 req/sec, 50k/day) — plenty for scouting.",
        keyless_alt="none — retailer stock is not otherwise legitimately "
                    "watchable (their pages bot-wall automated access)."),
    Provider(
        slug="google-maps",
        name="Google Places / Geocoding API",
        unlocks="Store ADDRESSES + closest→farthest distance from a "
                "member's zip — the 'which Targets near me, nearest first, "
                "with addresses' feature.",
        env_vars=["GOOGLE_MAPS_API_KEY"],
        signup_url="https://console.cloud.google.com/",
        steps=[
            "Open https://console.cloud.google.com/ → create a project",
            "APIs & Services → Enable APIs → enable 'Places API' + "
            "'Geocoding API'",
            "You must add a billing account (free tier is generous; set a "
            "budget cap so it never charges)",
            "Credentials → Create credentials → API key → copy it",
            "RESTRICT the key (API restrictions → Places + Geocoding only) "
            "so a leak is harmless",
            "Vault it: sov keys onboard google-maps",
        ],
        free=True, time_note="~15 min (billing setup is the slow part)",
        scope="Restrict to Places API + Geocoding API only",
        probe="probe_google_maps",
        tos_note="Official Google Cloud — free monthly credit covers scout "
                 "use; set a budget cap. Restrict the key to two APIs.",
        keyless_alt="Open-Meteo geocoding is free+keyless but has no store "
                    "data — Google is needed for real store addresses."),
    Provider(
        slug="ebay",
        name="eBay Developer API",
        unlocks="Sold + active listing comps → 'is this deal actually "
                "good?' pricing intelligence beside each find.",
        env_vars=["EBAY_APP_ID"],
        signup_url="https://developer.ebay.com/join",
        steps=[
            "Open https://developer.ebay.com/join → create a developer "
            "account",
            "Application Keys → create a PRODUCTION keyset",
            "Copy the 'App ID (Client ID)'",
            "Vault it: sov keys onboard ebay",
        ],
        free=True, time_note="~10 min",
        scope="Browse API (public data — no user OAuth needed)",
        probe="probe_ebay",
        tos_note="Official eBay developer program — free tier, ToS-compliant.",
        keyless_alt="none for structured comps."),
    Provider(
        slug="stripe",
        name="Stripe (restricted key)",
        unlocks="Round-2 auto-roles: buyers get their Subscriber/Tracker "
                "role automatically; cancellations handled.",
        env_vars=["STRIPE_SECRET_KEY"],
        signup_url="https://dashboard.stripe.com/apikeys",
        steps=[
            "Stripe Dashboard → Developers → API keys",
            "Create restricted key → read-only on Subscriptions + Customers",
            "Copy it (starts with rk_live_)",
            "Vault it: sov keys onboard stripe",
        ],
        free=True, time_note="~5 min",
        scope="RESTRICTED: read-only Subscriptions + Customers",
        probe="probe_stripe_key",
        tos_note="Your own Stripe account. A restricted key can't move money "
                 "even if leaked.",
        keyless_alt="none — needed for automated entitlement."),
    # lego-d (Kevin, 2026-07-18): "is there an official LEGO API?" —
    # honest answer: no official LEGO *deal* API exists. The real,
    # trustworthy lanes are Brickset (set DATA, free key) + BrickLink
    # (marketplace PRICES, OAuth). Both official developer programs.
    Provider(
        slug="brickset",
        name="Brickset API (LEGO set data)",
        unlocks="Official LEGO set metadata — retiring dates, RRP, themes, "
                "piece counts — so the 🧱 LEGO tracker can say 'retiring "
                "soon' and 'below RRP' with real data behind it.",
        env_vars=["BRICKSET_API_KEY"],
        signup_url="https://brickset.com/tools/webservices/requestkey",
        steps=[
            "Create a free Brickset account (brickset.com → Sign up)",
            "Open https://brickset.com/tools/webservices/requestkey",
            "Fill the short form (personal/project use) → the key is "
            "emailed to you",
            "Vault it: sov keys onboard brickset",
        ],
        free=True, time_note="~10 min (key arrives by email)",
        scope="read-only set data (the API's default)",
        probe="probe_brickset",
        tos_note="Official Brickset web services — free for non-commercial "
                 "volume, ToS-compliant. Brickset is fan-run, LEGO-blessed "
                 "set data — NOT a deals feed (Slickdeals covers deals).",
        keyless_alt="the 🧱 LEGO tracker already watches deal feeds — this "
                    "ADDS set intelligence on top."),
    Provider(
        slug="bricklink",
        name="BrickLink API (LEGO marketplace)",
        unlocks="Price-guide comps from the world's biggest LEGO "
                "marketplace — what a set ACTUALLY sells for, new vs used, "
                "beside every LEGO find.",
        env_vars=["BRICKLINK_CONSUMER_KEY", "BRICKLINK_CONSUMER_SECRET",
                  "BRICKLINK_TOKEN", "BRICKLINK_TOKEN_SECRET"],
        signup_url="https://www.bricklink.com/v2/api/register_consumer.page",
        steps=[
            "Create a BrickLink account (bricklink.com → Register)",
            "Open https://www.bricklink.com/v2/api/register_consumer.page",
            "Register as an API consumer (your IP is fine for 'server IP')",
            "BrickLink issues FOUR values: consumer key, consumer secret, "
            "access token, token secret — copy all four",
            "Vault them: sov keys onboard bricklink (pastes all four)",
        ],
        free=True, time_note="~15 min",
        scope="read-only price guide (never list/buy/sell scopes)",
        probe="probe_bricklink",
        tos_note="Official BrickLink developer API — free, OAuth-signed, "
                 "ToS-compliant. Owned by the LEGO Group.",
        keyless_alt="none for real marketplace comps."),
    # trading-signals-d (Kevin, 2026-08-01): "Alpaca trading api for the
    # live data, but not their broker api... do not want to make real
    # trades with their system." Alpaca ties market-data + trading to
    # the SAME account/keys (no separate data-only credential type,
    # confirmed 2026-08-01) -- the real safety boundary is architectural:
    # our code never calls an order-placement endpoint, not a key scope.
    # A free PAPER account is the right fit anyway: no KYC, instant,
    # real live market data, zero real trades possible even if a bug
    # ever did call an order endpoint.
    Provider(
        slug="alpaca",
        name="Alpaca Market Data API (paper account)",
        unlocks="Live + historical market data for the momentum-breakout "
                "signal bot (buy/sell alerts) -- data only, this account "
                "never places a real trade.",
        env_vars=["ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"],
        signup_url="https://app.alpaca.markets/signup",
        steps=[
            "Sign up at https://app.alpaca.markets/signup (email + "
            "password) -- PAPER trading, no KYC, no identity verification",
            "Set up MFA when prompted (required before API key use)",
            "Make sure the dashboard is in PAPER mode (not live)",
            "Dashboard -> API Keys panel -> generate Key + Secret",
            "Copy both immediately -- the secret is shown only once",
            "Vault them: sov keys onboard alpaca (paste key, then secret)",
        ],
        free=True, time_note="~5 min, instant, no KYC (paper account)",
        scope="Paper trading account -- real live data, simulated-only "
              "trades. Our code never calls Alpaca's order-placement "
              "endpoints regardless.",
        probe="",  # TODO: probe_alpaca once credentials.py is reachable
                   # again -- .claude/settings.json's credentials* deny
                   # glob currently blocks editing that file; flagged to
                   # Kevin, not fixed autonomously (settings.json edits
                   # are classifier-blocked without his direct action).
        tos_note="Official Alpaca Markets API -- free tier, ToS-compliant. "
                 "Paper accounts trade zero real money by design.",
        keyless_alt="none -- Alpaca requires an account+key even for "
                    "market data, no public/unauthenticated tier."),
    # ── keyless / public: already working, nothing to gather ──
    Provider(
        slug="nhtsa",
        name="NHTSA vPIC (vehicle data)",
        unlocks="Official US vehicle data — VIN decode, make/model/year, "
                "recalls — backing the 🚗 VEHICLES lane with government "
                "truth. Data, not deals (deal feeds cover deals).",
        env_vars=[], signup_url="", steps=[],
        keyless=True, time_note="free, keyless, official",
        tos_note="US government open data (vpic.nhtsa.dot.gov) — free, "
                 "keyless, no account.",
        keyless_alt="in use whenever the vehicles lane needs specs."),
    Provider(
        slug="weather",
        name="Open-Meteo (weather)",
        unlocks="Live weather in her voice (/ask, /ma, #ask-aria).",
        env_vars=[], signup_url="", steps=[],
        keyless=True, time_note="already live",
        tos_note="Free, keyless, open-data. No account, no key.",
        keyless_alt="in use now — nothing to do."),
    Provider(
        slug="deal-feeds",
        name="Slickdeals + Reddit RSS",
        unlocks="Every tracker's restock/deal finds (54 niches, "
                "Slickdeals-first).",
        env_vars=[], signup_url="", steps=[],
        keyless=True, time_note="already live",
        tos_note="Public RSS feeds — keyless, ToS-compliant with a proper "
                 "User-Agent (we send one).",
        keyless_alt="Slickdeals is genuinely live keyless; the Reddit half "
                    "is NOT (anonymous endpoint rate-limited to zero "
                    "throughput fleet-wide) — the Reddit API key is the "
                    "real fix for that half, not just a limit-raiser."),
]

PROVIDERS_BY_SLUG = {p.slug: p for p in PROVIDERS}


def get_provider(slug: str) -> Provider | None:
    return PROVIDERS_BY_SLUG.get((slug or "").strip().lower())


def gatherable() -> list[Provider]:
    """Providers that need a human to fetch a key (the concierge list)."""
    return [p for p in PROVIDERS if not p.keyless]


def keyless() -> list[Provider]:
    """Already-covered public sources — nothing to gather."""
    return [p for p in PROVIDERS if p.keyless]


def status(stored_keys: dict) -> list[dict]:
    """Per-provider: have we got its key(s)? what does it unlock/block?"""
    out = []
    for p in gatherable():
        have = all(bool((stored_keys or {}).get(v)) for v in p.env_vars)
        out.append({"slug": p.slug, "name": p.name, "have": have,
                    "unlocks": p.unlocks, "env_vars": p.env_vars})
    return out


def render_status(stored_keys: dict) -> str:
    """The 'what's unlocked vs blocked' view."""
    lines = ["🔑 Key Concierge — what's unlocked vs what's waiting", ""]
    for s in status(stored_keys):
        mark = "✓ unlocked" if s["have"] else "○ waiting"
        lines.append(f"{mark}  {s['name']}")
        lines.append(f"     {s['unlocks']}")
        if not s["have"]:
            lines.append(f"     → get it: sov keys onboard {s['slug']}")
        lines.append("")
    lines.append("keyless & already working: "
                 + ", ".join(p.name for p in keyless()))
    lines.append("full walkthrough: KEY_GATHERING.md (sov docs)")
    return "\n".join(lines)


__all__ = ["Provider", "PROVIDERS", "PROVIDERS_BY_SLUG", "get_provider",
           "gatherable", "keyless", "status", "render_status"]
