"""verticals.py — 🌐 the money map: every trackable niche, as data.

Kevin's ask (2026-07-17): "what else can we track and make money with?
shoes, clothes, dozens or hundreds of things." The proven key from
building the scout: **Slickdeals search RSS + Reddit sub/search RSS work
for ANY query**, so nearly every niche with a deal-hunting community is
watchable with our existing reliable lanes.

retailer-scrape-d (Kevin, 2026-07-27): the original "no retailer
scraping, no anti-bot evasion" boundary above is LIFTED, deliberately —
Kevin evaluated the official-API path (Best Buy's free developer API
included) and chose direct scraping instead, eyes open on the real
tradeoffs (ToS exposure, no guaranteed success against Cloudflare/Akamai/
PerimeterX-grade protection, ongoing maintenance as sites change). See
`discord_runtime/stealth_browser.py` + `ScrapeFetcher` (fetchers.py) —
still ALERT-only, never auto-buy.

Each Vertical is one entry here; adding a niche = one row. `sov scout
sync` turns this catalog into fleet projects (one per vertical), each
routing finds to its tracker channel. Priority verticals (tier="star")
show on the Hub's front row + get a sellable bot; the rest live one
"▸ View more" click deep (Kevin's design).

Source builders (pure, reliable, rate-friendly):
  • slickdeals(q)   → deal aggregator search RSS (any query)
  • reddit_sub(s)   → a subreddit's /new RSS
  • reddit_search(sub, q) → in-subreddit search RSS
  • scrape(url)     → a single page, fetched via the hardened stealth
                       browser (kind="scrape") — direct retailer sites
                       with no reliable RSS/API lane
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field


def slickdeals(query: str) -> tuple[str, str, str]:
    q = urllib.parse.quote_plus(query)
    return (f"sd-{_slug(query)}",
            f"https://slickdeals.net/newsearch.php?searcharea=deals"
            f"&searchin=first&rss=1&q={q}", "rss")


def reddit_sub(sub: str) -> tuple[str, str, str]:
    return (f"r-{sub.lower()}", f"https://www.reddit.com/r/{sub}/new/.rss", "rss")


def reddit_search(sub: str, query: str) -> tuple[str, str, str]:
    q = urllib.parse.quote_plus(query)
    return (f"r-{sub.lower()}-{_slug(query)}",
            f"https://www.reddit.com/r/{sub}/search.rss"
            f"?q={q}&restrict_sr=1&sort=new", "rss")


def scrape(name: str, url: str) -> tuple[str, str, str]:
    """retailer-scrape-d: a single page fetched via the hardened stealth
    browser (fetchers.ScrapeFetcher) — for direct retailer sites with no
    reliable RSS/API lane. `name` is a short, unique-per-vertical slug
    (e.g. "target-gpu-search"), not derived from `url` — retailer URLs
    don't slugify into anything readable."""
    return (name, url, "scrape")


def warframe_flip(category: str) -> tuple[str, str, str]:
    """warframe-flip-d (Kevin, 2026-07-27), refined after "Well I wanted
    a whole warframe category, with channels for item types": one
    source per item TYPE (`category`: "set" | "relic" | "arcane" |
    "riven"), each with its own independent rotation through that
    category's real warframe.market pool (see `WarframeFlipFetcher` in
    fetchers.py). `category` rides in `url` — a marker, not a real URL,
    same convention `scrape()` established for non-HTTP fetchers."""
    return (f"wf-flip-{category}", category, "warframe-flip")


def osrs_flip(tier: str) -> tuple[str, str, str]:
    """osrs-flips-d (Kevin, 2026-08-03): one source per CAPITAL TIER
    ("starter" | "mid" | "high" | "volume"). Tier is the axis that
    actually matters in OSRS — a new account cannot flip a Twisted Bow,
    and a whale does not care about a 600gp margin — so segmenting by
    bankroll is what makes the feed usable instead of taunting.
    `tier` rides in `url` as a marker, same convention as scrape() and
    warframe_flip()."""
    return (f"osrs-flip-{tier}", tier, "osrs-flip")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:24]


# universal noise filters — graded/scam/proxy junk nobody's paying to hear
COMMON_EXCLUDES = ["graded", "psa ", "cgc ", "slab", "proxy", "fake",
                   "replica", "custom made", "sticker"]

STAR = "star"        # front-row Hub button + sellable bot
DEEP = "deep"        # lives under "▸ View more"


@dataclass(frozen=True)
class Vertical:
    slug: str                       # project slug (scout-<slug>)
    name: str                       # display name
    emoji: str                      # one classifier-safe glyph in practice
    color: int
    tier: str                       # STAR | DEEP
    lane: str                       # deals | online | local
    sources: list[tuple[str, str, str]]  # (source_name, url, kind)
    rank_keywords: list[str] = field(default_factory=list)  # hot=front
    excludes: list[str] = field(default_factory=lambda: list(COMMON_EXCLUDES))
    channel: str = ""               # tracker channel (defaults track-<slug>)
    price_cents: int = 700          # sellable per-bot monthly
    blurb: str = ""
    # zip/radius descope (Kevin, 2026-07-29): "we really only need
    # the zip radius as an optional feature per tracker... for TCGs
    # that is what we most need it for and squishmallows." Off by
    # default; only verticals tied to physical pickup turn it on.
    geo_filter_enabled: bool = False
    # mead-lock-d (Kevin, 2026-08-03): normally `sov scout sync` derives the
    # webhook env name from the slug (DISCORD_TRACK_<SLUG>_WEBHOOK_URL). A
    # vertical that posts into a channel minted by some OTHER mechanism —
    # mead-deals lives in the hand-written, age-gated MEAD LOUNGE — already
    # has a webhook under a different name, and the derived one is empty.
    # That mismatch is exactly why #mead-deals sat silent for 400+ hours
    # while everything upstream looked fine. Set this to point at the real
    # one; blank keeps the derived default.
    webhook_env: str = ""

    @property
    def project(self) -> str:
        return f"scout-{self.slug}"

    @property
    def track_channel(self) -> str:
        return self.channel or f"track-{self.slug}"

    @property
    def ping_role(self) -> str:
        return f"Track-{self.slug.title().replace('-', '')}"


def _v(slug, name, emoji, color, tier, lane, sources, kws, blurb,
       price=700, channel="", excludes=None, geo_filter_enabled=False,
       webhook_env=""):
    return Vertical(slug=slug, name=name, emoji=emoji, color=color, tier=tier,
                    lane=lane, sources=sources, rank_keywords=kws, blurb=blurb,
                    price_cents=price, channel=channel,
                    excludes=excludes if excludes is not None
                    else list(COMMON_EXCLUDES),
                    geo_filter_enabled=geo_filter_enabled,
                    webhook_env=webhook_env)


# ── THE CATALOG ─────────────────────────────────────────────────────────────
# Pokémon stays its own live project (scout-pokemon aliases the shipped
# tcg-scout data via sync); everything else is new.
CATALOG: list[Vertical] = [
    # 🗡 OLD SCHOOL RUNESCAPE — osrs-flips-d (Kevin, 2026-08-03).
    # Grand Exchange flipping off the official wiki price API (no auth,
    # identifying UA per their policy). Channels split by capital tier,
    # not item type: that is the real constraint on a player.
    _v("osrs-starter", "OSRS: Starter Flips", "\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("starter")],
       ["flip", "margin"],
       "Grand Exchange flips under 10k a unit — high ROI, small bankroll. "
       "Margins are AFTER the 1% GE tax, with buy limits and 24h volume.",
       price=700, channel="osrs-starter", excludes=[]),
    _v("osrs-mid", "OSRS: Mid Flips", "\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("mid")],
       ["flip", "margin"],
       "Grand Exchange flips from 10k to 1M a unit, ranked by real profit "
       "per 4h buy-limit window.",
       price=700, channel="osrs-mid", excludes=[]),
    _v("osrs-high", "OSRS: High-Cap Flips", "\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("high")],
       ["flip", "margin"],
       "Grand Exchange flips over 1M a unit — big margins, tight buy "
       "limits, so ranked on what you can actually clear per window.",
       price=700, channel="osrs-high", excludes=[]),
    _v("osrs-volume", "OSRS: High-Volume Flips", "\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("volume")],
       ["flip", "margin"],
       "The fastest-moving items on the GE — thin margins, but they fill "
       "immediately. Ranked by 24h volume.",
       price=700, channel="osrs-volume", excludes=[]),
    # 🃏 cards & collectibles
    _v("pokemon", "Pokémon TCG", "🃏", 0xF1C40F, STAR, "deals",
       [slickdeals("pokemon tcg"), slickdeals("pokemon elite trainer"),
        slickdeals("pokemon booster"), reddit_sub("PkmnTCGDeals"),
        reddit_sub("PokemonTCGDeals"),
        # retailer-scrape-d (Kevin, 2026-07-27): direct Pokémon Center
        # coverage via the hardened stealth browser (ScrapeFetcher).
        # Confirmed via live probe: pokemoncenter.com currently returns
        # HTTP 403 to the hardened session — the per-host cooldown
        # (fetchers._note_outcome) engages correctly on this, so it's
        # wired but will sit quiet/backing-off until it clears or the
        # session hardening improves further. Best-effort, by design.
        scrape("pokemoncenter-tcg-search",
              "https://www.pokemoncenter.com/search/tcg")],
       ["prismatic", "151", "crown zenith", "surging sparks", "elite trainer",
        "etb", "booster box", "booster bundle"],
       "Pokémon restocks + deals, ranked by set value.", price=800,
       geo_filter_enabled=True),
    _v("mtg", "Magic: The Gathering", "🔮", 0x9B59B6, STAR, "deals",
       [slickdeals("magic the gathering"), reddit_sub("mtgfinance"),
        reddit_search("magicTCG", "deal OR restock")],
       ["collector booster", "commander", "secret lair", "bundle", "set booster"],
       "MTG sealed + Secret Lair drops + deals."),
    _v("yugioh", "Yu-Gi-Oh!", "🎴", 0x34495E, STAR, "deals",
       [slickdeals("yugioh"), reddit_search("yugioh", "deal OR restock")],
       ["structure deck", "tin", "collection", "booster box", "ghost rare"],
       "Yu-Gi-Oh sealed + deals."),
    _v("lorcana", "Disney Lorcana", "🏰", 0x2980B9, DEEP, "deals",
       [slickdeals("disney lorcana"), reddit_search("Lorcana", "deal OR restock")],
       ["illumineer", "trove", "booster", "starter", "gift set"],
       "Lorcana restocks + deals."),
    _v("onepiece-tcg", "One Piece TCG", "🏴‍☠️", 0xE74C3C, DEEP, "deals",
       [slickdeals("one piece card game"),
        reddit_search("OnePieceTCG", "deal OR restock")],
       ["booster box", "starter deck", "premium"],
       "One Piece card game restocks + deals."),
    _v("sportscards", "Sports Cards", "🏈", 0x16A085, DEEP, "deals",
       [slickdeals("panini prizm"), slickdeals("topps chrome"),
        reddit_sub("sportscarddeals")],
       ["hobby box", "blaster", "mega box", "prizm", "chrome"],
       "Panini/Topps sealed + deals."),
    _v("funko", "Funko Pop", "🧸", 0xE67E22, STAR, "deals",
       [slickdeals("funko pop"), reddit_search("funkopop", "deal OR exclusive")],
       ["exclusive", "chase", "grail", "vaulted", "convention"],
       "Funko exclusives + chase + deals."),
    _v("lego", "LEGO", "🧱", 0xE74C3C, STAR, "deals",
       [slickdeals("lego"), reddit_sub("legodeal"),
        reddit_search("lego", "retiring OR deal")],
       ["retiring", "exclusive", "ucs", "modular", "gwp", "star wars",
        "botanical"],
       "LEGO retiring sets, exclusives + deals.", price=800),
    _v("hotwheels", "Hot Wheels", "🏎", 0xC0392B, DEEP, "deals",
       [slickdeals("hot wheels"), reddit_search("HotWheels", "deal OR find")],
       ["treasure hunt", "rlc", "super", "premium", "team transport"],
       "Hot Wheels chase + deals."),
    _v("collectibles", "Blind-box & Plush", "✨", 0x8E44AD, DEEP, "deals",
       [slickdeals("sonny angel"), slickdeals("jellycat"),
        slickdeals("smiski"), reddit_search("Sonnyangel", "deal OR restock")],
       ["exclusive", "limited", "rare", "grail", "blind box"],
       "Sonny Angel, Jellycat, Smiski + blind-box."),
    _v("squishmallows", "Squishmallows", "🫧", 0xE91E63, DEEP, "deals",
       [slickdeals("squishmallow"), reddit_sub("squishmallow"),
        reddit_search("squishmallow", "deal OR restock OR find")],
       ["axolotl", "exclusive", "hard to find", "htf", "limited", "drop",
        "grail", "connetix"],
       "Squishmallows drops, exclusives + deals — the plush resale market."),

    # 👟 sneakers & streetwear
    _v("sneakers", "Sneakers", "👟", 0x2C3E50, STAR, "online",
       [reddit_sub("sneakers"), reddit_sub("SNKRS"),
        slickdeals("nike jordan"), slickdeals("new balance")],
       ["jordan", "yeezy", "dunk", "sb", "travis", "collab", "og",
        "limited", "restock"],
       "Nike/Jordan/Yeezy drops + restocks. We alert; you cop.", price=800),
    _v("streetwear", "Streetwear & Apparel", "🧥", 0x1ABC9C, STAR, "online",
       [reddit_sub("supremeclothing"), reddit_sub("streetwearstartup"),
        slickdeals("supreme"), slickdeals("carhartt")],
       ["supreme", "drop", "collab", "box logo", "limited", "capsule"],
       "Supreme + streetwear drops + apparel deals."),
    # 👕 CLOTHING (clothing-d, Kevin 2026-07-18): a real category — mens /
    # womens / childrens each in their own channel; kids' toys too ("kids
    # stuff can generate a lot of money"). Slickdeals-first.
    _v("fashion-deals", "Women's Clothes", "👗", 0xE84393, DEEP, "deals",
       [slickdeals("womens clothing"), slickdeals("lululemon"),
        slickdeals("clothing clearance")],
       ["clearance", "we made too much", "sale", "final", "coupon", "dress"],
       "Women's clothing deals — sales, clearance + we-made-too-much.",
       channel="womens-clothes"),
    _v("mens-clothes", "Men's Clothes", "👔", 0x2C3E50, DEEP, "deals",
       [slickdeals("mens clothing"), slickdeals("mens jeans"),
        reddit_sub("frugalmalefashion")],
       ["clearance", "sale", "coupon", "boots", "jacket", "final"],
       "Men's clothing deals — everyday staples to jackets + boots.",
       channel="mens-clothes"),
    _v("childrens-clothes", "Children's Clothes", "🧒", 0xF39C12, DEEP, "deals",
       [slickdeals("kids clothing"), slickdeals("baby clothes"),
        slickdeals("carters")],
       ["clearance", "sale", "bundle", "carters", "size", "baby"],
       "Kids' + baby clothing deals — growing wardrobes for less.",
       channel="childrens-clothes"),
    _v("childrens-toys", "Children's Toys", "🎠", 0xE67E22, DEEP, "deals",
       [slickdeals("kids toys"), slickdeals("toy clearance"),
        slickdeals("melissa and doug")],
       ["clearance", "sale", "stem", "playset", "board book", "outdoor"],
       "Kids' toy deals — clearance runs, playsets + STEM finds.",
       channel="childrens-toys"),
    _v("accessories", "Accessories", "👜", 0x884EA0, DEEP, "deals",
       [slickdeals("handbag"), slickdeals("sunglasses"),
        slickdeals("jewelry deal")],
       ["clearance", "sale", "leather", "designer", "gift"],
       "Bags, sunglasses, jewelry + the finishing touches.",
       channel="accessories"),

    # 🖥 tech & gaming hardware
    # computers-d (Kevin, 2026-07-18): the star PC-parts tracker now lives
    # in 💻 COMPUTERS as #desktop-parts — one home, no twin channels.
    _v("gpus", "GPUs & PC Parts", "🔩", 0x27AE60, STAR, "deals",
       [slickdeals("rtx graphics card"), slickdeals("ssd"),
        slickdeals("motherboard"), slickdeals("power supply"),
        reddit_sub("buildapcsales")],
       ["rtx 50", "rtx 40", "radeon", "gpu", "graphics card", "restock", "9800x3d"],
       "GPU/CPU/SSD + desktop-part restocks and price drops.", price=800,
       channel="desktop-parts"),
    # 🎮 GAMING (gaming-d, Kevin 2026-07-18): consoles (hardware) + games,
    # kept in SEPARATE channels under the GAMING category, retro → modern.
    _v("consoles", "Consoles & Handhelds", "🎮", 0x2980B9, STAR, "deals",
       [slickdeals("ps5"), slickdeals("nintendo switch"),
        slickdeals("steam deck"), reddit_search("consoledeals", "restock OR deal")],
       ["ps5", "xbox", "switch 2", "steam deck", "rog ally", "restock", "bundle"],
       "PS5/Xbox/Switch + handheld restocks + deals.", price=800,
       channel="modern-consoles"),
    _v("retro-consoles", "Retro Consoles", "🕹", 0x9B59B6, DEEP, "deals",
       [slickdeals("retro console"), slickdeals("super nintendo"),
        reddit_sub("consoledeals"),
        reddit_search("retrogaming", "deal OR sale OR restock")],
       ["snes", "nes", "genesis", "n64", "gamecube", "dreamcast", "ps1",
        "ps2", "retro", "cib", "sealed", "console"],
       "Legacy console hardware — NES/SNES/Genesis/N64/PS1-2/Dreamcast.",
       channel="retro-consoles"),
    # 💻 COMPUTERS (computers-d, Kevin 2026-07-18): whole machines + parts,
    # each in its OWN channel. Slickdeals-first — Kevin: "the Reddit rate
    # limit is too soft, we need other API sources"; reddit only as garnish.
    _v("desktops", "Desktops", "🖥", 0x2E86C1, DEEP, "deals",
       [slickdeals("gaming desktop"), slickdeals("desktop pc"),
        slickdeals("mini pc")],
       ["prebuilt", "rtx", "ryzen", "clearance", "open box", "refurb"],
       "Full desktop + prebuilt PC deals — gaming rigs to mini PCs.",
       channel="desktops"),
    _v("servers", "Servers & Homelab", "🗄", 0x117A65, DEEP, "deals",
       [slickdeals("home server"), slickdeals("rack server"),
        slickdeals("synology nas"), reddit_sub("homelabsales")],
       ["nas", "rack", "xeon", "epyc", "ecc", "refurb", "off lease"],
       "Server + homelab deals — NAS boxes, racks, off-lease iron.",
       channel="servers"),
    _v("laptops", "Laptops", "💻", 0x1F618D, DEEP, "deals",
       [slickdeals("gaming laptop"), slickdeals("laptop deal"),
        slickdeals("thinkpad")],
       ["rtx", "oled", "thinkpad", "clearance", "open box", "refurb"],
       "Laptop deals — gaming, business, and clearance finds.",
       channel="laptops"),
    _v("phones", "Phones", "📱", 0x6C3483, DEEP, "deals",
       [slickdeals("iphone"), slickdeals("samsung galaxy"),
        slickdeals("google pixel"), slickdeals("smartphone deal")],
       ["unlocked", "trade in", "preorder", "clearance", "renewed"],
       "Phone deals — iPhone/Galaxy/Pixel, unlocked + carrier.",
       channel="phones"),
    _v("server-parts", "Server Parts", "🛠", 0x0E6251, DEEP, "deals",
       [slickdeals("ecc ram"), slickdeals("enterprise ssd"),
        slickdeals("nas hard drive")],
       ["ecc", "sas", "u.2", "10gbe", "enterprise", "refurb"],
       "Server internals — ECC RAM, enterprise drives, NICs.",
       channel="server-parts"),
    _v("laptop-parts", "Laptop Parts", "🔧", 0x21618C, DEEP, "deals",
       [slickdeals("laptop ram"), slickdeals("laptop ssd"),
        slickdeals("laptop battery")],
       ["sodimm", "nvme", "battery", "charger", "dock"],
       "Laptop upgrades — RAM, NVMe drives, batteries, docks.",
       channel="laptop-parts"),
    _v("phone-parts", "Phone Parts & Power", "🔌", 0x5B2C6F, DEEP, "deals",
       [slickdeals("usb c charger"), slickdeals("phone battery"),
        slickdeals("screen protector")],
       ["gan", "magsafe", "power bank", "fast charge", "replacement"],
       "Phone accessories + repair — chargers, batteries, screens.",
       channel="phone-parts"),
    _v("apple", "Apple & Audio", "🍎", 0x95A5A6, DEEP, "deals",
       [slickdeals("apple airpods"), slickdeals("macbook"),
        slickdeals("sony headphones")],
       ["airpods", "macbook", "ipad", "apple watch", "sony wh", "bose"],
       "Apple + premium audio deals."),
    _v("keyboards", "Keyboards & EDC", "⌨", 0x7F8C8D, DEEP, "deals",
       [reddit_sub("mechmarket"), slickdeals("mechanical keyboard"),
        reddit_search("MechanicalKeyboards", "group buy OR drop")],
       ["group buy", "drop", "gmk", "keycap", "in stock"],
       "Mechanical keyboard drops + EDC."),

    # 🎮 games & entertainment
    _v("freegames", "Free Games", "🆓", 0x2ECC71, STAR, "deals",
       [reddit_sub("FreeGameFindings"), slickdeals("free game epic")],
       ["free", "epic", "prime gaming", "gog", "claim", "giveaway"],
       "Free game giveaways (Epic/Prime/GOG) — pure value.", price=500,
       channel="free-games"),
    _v("gamedeals", "Game Deals", "🕹", 0x8E44AD, DEEP, "deals",
       [reddit_sub("GameDeals"), slickdeals("video game sale")],
       ["historical low", "collector", "steelbook", "preorder", "bundle"],
       "Video game price drops + collector editions.",
       channel="game-deals"),
    _v("retro-games", "Retro Games", "👾", 0xE67E22, DEEP, "deals",
       [reddit_sub("gamecollecting"), slickdeals("retro video game"),
        reddit_search("retrogaming", "deal OR sale")],
       ["cib", "sealed", "complete", "cartridge", "retro", "rare",
        "collector", "n64", "snes"],
       "Old + collectible games — cartridges, sealed, collector titles.",
       channel="retro-games"),
    _v("media", "Movies, Vinyl & Manga", "💿", 0x34495E, DEEP, "deals",
       [slickdeals("4k steelbook"), slickdeals("vinyl record"),
        reddit_search("vinyldeals", "deal OR restock")],
       ["steelbook", "4k", "limited pressing", "boxset", "omnibus"],
       "4K steelbooks, vinyl pressings + manga."),

    # 🛒 deals, clearance & arbitrage
    _v("deals", "Hot Deals Radar", "🔥", 0xE74C3C, STAR, "deals",
       [reddit_sub("deals"), reddit_sub("Flipping"),
        slickdeals("frontpage")],
       ["clearance", "lightning", "historical low", "price error", "coupon"],
       "The best deals + flip opportunities, all day.", price=600),
    _v("clearance", "Store Clearance", "🏷", 0xD35400, DEEP, "local",
       [slickdeals("target clearance"), slickdeals("walmart clearance"),
        reddit_search("Clearance", "target OR walmart")],
       ["penny", "clearance", "markdown", "hidden", "ymmv"],
       "Target/Walmart clearance + penny finds."),
    _v("dollar-general", "Dollar General Finds", "🏪", 0x27AE60, DEEP, "local",
       [slickdeals("dollar general pokemon"),
        reddit_search("PokeInvesting", "dollar general")],
       ["restock", "found", "in stock", "reset", "penny"],
       "Dollar General shelf finds — go check your store."),
    _v("giftcards", "Gift Card Deals", "💳", 0x16A085, DEEP, "deals",
       [slickdeals("gift card discount"), reddit_sub("GiftCardExchange")],
       ["discount", "% off", "bonus", "promo"],
       "Discounted gift cards — instant arbitrage."),

    # 🏠 hobby & enthusiast
    _v("warhammer", "Warhammer & Wargames", "⚔", 0x7F8C8D, DEEP, "deals",
       [slickdeals("warhammer"), reddit_search("Warhammer40k", "deal OR restock")],
       ["box set", "combat patrol", "codex", "limited", "restock"],
       "Games Workshop restocks + wargame deals."),
    _v("boardgames", "Board Games", "🎲", 0x2980B9, DEEP, "deals",
       [reddit_sub("boardgamedeals"), slickdeals("board game")],
       ["kickstarter", "deluxe", "historical low", "expansion"],
       "Board game deals + crowdfunding."),
    _v("camera", "Camera & Drones", "📷", 0x34495E, DEEP, "deals",
       [slickdeals("camera lens"), slickdeals("dji drone"),
        reddit_search("photomarket", "deal OR sale")],
       ["refurbished", "open box", "deal", "bundle", "lens"],
       "Camera bodies, lenses + drone deals."),
    _v("watches", "Watches", "⌚", 0x2C3E50, DEEP, "deals",
       [slickdeals("watch deal"), reddit_sub("Watchexchange")],
       ["microbrand", "drop", "limited", "seiko", "diver"],
       "Microbrand drops + watch deals."),
    _v("beauty", "Beauty & Fragrance", "💄", 0xE84393, DEEP, "deals",
       [slickdeals("sephora sale"), slickdeals("fragrance deal"),
        reddit_search("MUAontheCheap", "deal OR sale")],
       ["sale", "gift with purchase", "clearance", "decant", "limited"],
       "Sephora/Ulta sales + fragrance deals."),
    # mead-lock-d (Kevin, 2026-08-03): "we need to get the mead bot locked
    # in." Kept out of the retirement sweep — MEAD LOUNGE is a real, named
    # category with its own age gate, not a generic shelf. Two changes that
    # make it actually fire: it posts into the EXISTING #mead-deals channel
    # (channel=) via the webhook that already exists (webhook_env=), and the
    # two Reddit sources are dropped — measured 2026-08-03 they had 0 successes
    # in 255 attempts fleet-wide, while sd-honey and sd-home-brewing had
    # 1,296 and 1,294 successes with 0 and 2 failures.
    _v("mead-brewing", "Mead & Homebrew Ingredients", "🍯", 0xD4A017, DEEP,
       "deals",
       [slickdeals("honey"), slickdeals("home brewing")],
       ["honey", "yeast", "fermenter", "carboy", "nutrient", "brewing",
        "must", "airlock", "bulk"],
       "Honey, yeast, fermenters + brewing-gear deals for mead-makers "
       "(ingredients, all ages — the drinking's the 21+ part 😉).",
       channel="mead-deals",
       webhook_env="DISCORD_MEAD_DEALS_WEBHOOK_URL"),
    _v("coffee", "Coffee & Kitchen", "☕", 0x8B4513, DEEP, "deals",
       [slickdeals("espresso machine"), reddit_search("coffeedeals", "deal")],
       ["grinder", "espresso", "roaster", "clearance", "refurb"],
       "Coffee gear + kitchen deals."),

    # 🚗 VEHICLES (vehicles-d, Kevin 2026-07-18): honest lanes — deal feeds
    # for leases/EVs + parts now; eBay Motors comps light up when the eBay
    # key lands (concierge); NHTSA vPIC = free official vehicle DATA.
    _v("vehicles", "Vehicles", "🚗", 0xB03A2E, DEEP, "deals",
       [slickdeals("car lease"), slickdeals("ev deal"),
        slickdeals("certified pre owned")],
       ["lease", "ev", "tax credit", "apr", "incentive", "certified"],
       "Vehicle deals — lease specials, EV incentives, CPO finds.",
       channel="vehicles"),
    _v("vehicle-parts", "Vehicle Parts", "⚙", 0x7B7D7D, DEEP, "deals",
       [slickdeals("tires"), slickdeals("motor oil"),
        slickdeals("car battery"), slickdeals("brake pads")],
       ["tires", "rebate", "oil", "battery", "tool", "jack"],
       "Tires, oil, batteries, brakes + garage tool deals.",
       channel="vehicle-parts"),

    # 🐾 PETS (pets-d, Kevin 2026-07-18): food / toys / accessories, each
    # its own channel — recurring-spend niches people happily follow.
    _v("pet-food", "Pet Food", "🦴", 0xCA6F1E, DEEP, "deals",
       [slickdeals("dog food"), slickdeals("cat food"),
        slickdeals("cat litter")],
       ["autoship", "coupon", "grain free", "litter", "bulk", "stock up"],
       "Dog + cat food and litter deals — the stock-up alerts.",
       channel="pet-food"),
    _v("pet-toys", "Pet Toys", "🎾", 0x239B56, DEEP, "deals",
       [slickdeals("dog toy"), slickdeals("cat toy")],
       ["kong", "chew", "clearance", "interactive", "bundle"],
       "Dog + cat toy deals — enrichment for less.",
       channel="pet-toys"),
    _v("pet-accessories", "Pet Accessories", "🐾", 0x148F77, DEEP, "deals",
       [slickdeals("dog bed"), slickdeals("pet carrier"),
        slickdeals("aquarium")],
       ["bed", "crate", "harness", "carrier", "aquarium", "clearance"],
       "Beds, crates, harnesses, tanks + everything pets wear or ride in.",
       channel="pet-accessories"),

    # 📦 WHOLESALE (wholesale-d, Kevin 2026-07-18): what's HONESTLY
    # watchable now — pallet/lot/liquidation deal feeds + r/Flipping
    # garnish. True wholesale (Faire/Alibaba/B-Stock/Liquidation.com) =
    # accounts Kevin opens — concierge territory, never scraping.
    _v("wholesale-lots", "Wholesale & Lots", "📦", 0x873600, DEEP, "deals",
       [slickdeals("pallet"), slickdeals("bulk lot"),
        reddit_search("Flipping", "pallet OR lot OR wholesale")],
       ["pallet", "lot", "bulk", "case", "wholesale", "msrp"],
       "Pallet + bulk-lot finds — the flipper's supply line.",
       channel="wholesale-lots"),
    _v("liquidation", "Liquidation", "📉", 0x633974, DEEP, "deals",
       [slickdeals("liquidation"), slickdeals("open box"),
        slickdeals("woot")],
       ["liquidation", "open box", "refurb", "warehouse", "clearance"],
       "Liquidation, open-box + warehouse-deal alerts.",
       channel="liquidation"),

    # 🎟 events & everyday
    _v("travel", "Travel & Error Fares", "✈", 0x3498DB, DEEP, "deals",
       [reddit_sub("travel_deals"), slickdeals("flight deal")],
       ["error fare", "mistake fare", "glitch", "cheap flight", "points"],
       "Flight error-fares + travel deals — huge savings."),
    _v("tickets", "Concerts & Events", "🎟", 0x9B59B6, DEEP, "deals",
       [reddit_search("concert", "presale OR tour"),
        slickdeals("concert tickets")],
       ["presale", "tour", "on sale", "code"],
       "Tour presales + event drops."),

    # 🎯 TARGET category (Kevin, 2026-07-27): "add a target category for
    # squishmallows, pokemon, and devices, hardware, consoles, and
    # accessories." Replaces the earlier single lumped "target" tracker
    # (GPU + Pokémon search only) with one channel per item type, same
    # shape as BEST BUY below. Target's real product API is captcha-
    # walled (confirmed live, 2026-07-27) so these post via ScrapeFetcher's
    # default whole-page-change fallback, same honest behavior as before —
    # no fabricated per-product parsing. Channel names get a "target-"
    # prefix wherever Best Buy or another category already owns the bare
    # name (pokemon/devices/consoles/accessories); squishmallows + hardware
    # were free.
    _v("target-squishmallows", "Target: Squishmallows", "🎯", 0xCC0000, DEEP,
       "deals",
       [scrape("target-squishmallows-search",
              "https://www.target.com/s?searchTerm=squishmallow")],
       ["restock", "back in stock", "exclusive", "plush"],
       "Squishmallow restocks — direct Target.com watches.", price=800,
       channel="squishmallows", geo_filter_enabled=True),
    _v("target-pokemon", "Target: Pokémon", "🎯", 0xCC0000, DEEP, "deals",
       [scrape("target-pokemon-search",
              "https://www.target.com/s?searchTerm=pokemon+trading+cards")],
       ["restock", "back in stock", "pokemon", "tcg", "booster"],
       "Pokémon TCG restocks — direct Target.com watches.", price=800,
       channel="target-pokemon", geo_filter_enabled=True),
    _v("target-devices", "Target: Devices", "🎯", 0xCC0000, DEEP, "deals",
       [scrape("target-devices-search",
              "https://www.target.com/s?searchTerm=cell+phone")],
       ["restock", "back in stock", "phone", "tablet"],
       "Phones + tablets — direct Target.com watches.", price=800,
       channel="target-devices"),
    _v("target-hardware", "Target: Hardware", "🎯", 0xCC0000, DEEP, "deals",
       [scrape("target-hardware-search",
              "https://www.target.com/s?searchTerm=graphics+card")],
       ["restock", "back in stock", "gpu", "cpu", "computer parts"],
       "GPUs + computer hardware — direct Target.com watches.", price=800,
       channel="hardware"),
    _v("target-consoles", "Target: Consoles", "🎯", 0xCC0000, DEEP, "deals",
       [scrape("target-consoles-search",
              "https://www.target.com/s?searchTerm=gaming+console")],
       ["restock", "back in stock", "playstation", "xbox", "switch"],
       "Consoles + bundles — direct Target.com watches.", price=800,
       channel="target-consoles"),
    _v("target-accessories", "Target: Accessories", "🎯", 0xCC0000, DEEP,
       "deals",
       [scrape("target-accessories-search",
              "https://www.target.com/s?searchTerm=tech+accessories")],
       ["restock", "back in stock", "case", "charger", "cable"],
       "Cases, chargers, and tech accessories — direct Target.com watches.",
       price=800, channel="target-accessories"),

    # 🛒 SAM'S CLUB + 🔴 COSTCO (Kevin, 2026-07-27): "add sams club and
    # costco for squish mellows and pokemon also." Live-probed at build
    # time (2026-07-27): samsclub.com returns a "Let us know you're not a
    # robot" challenge on EVERY visit tried, including its own homepage
    # (no warm-up cleared it) — fully captcha-walled, same honest
    # whole-page-change fallback as Target's product API. costco.com
    # returns real 200s (~2.9MB pages, title "Search | Costco") but no
    # confirmed product-data markers found yet — real per-product
    # parsing is a follow-up once its actual data shape is captured; both
    # stay on ScrapeFetcher's default fallback for now, never fabricated.
    _v("samsclub-squishmallows", "Sam's Club: Squishmallows", "🛒", 0x0060A9,
       DEEP, "deals",
       [scrape("samsclub-squishmallows-search",
              "https://www.samsclub.com/s/squishmallow")],
       ["restock", "back in stock", "exclusive", "plush"],
       "Squishmallow restocks — direct SamsClub.com watches.", price=800,
       channel="samsclub-squishmallows", geo_filter_enabled=True),
    _v("samsclub-pokemon", "Sam's Club: Pokémon", "🛒", 0x0060A9, DEEP,
       "deals",
       [scrape("samsclub-pokemon-search",
              "https://www.samsclub.com/s/pokemon+trading+cards")],
       ["restock", "back in stock", "pokemon", "tcg", "booster"],
       "Pokémon TCG restocks — direct SamsClub.com watches.", price=800,
       channel="samsclub-pokemon", geo_filter_enabled=True),
    _v("costco-squishmallows", "Costco: Squishmallows", "🔴", 0xE01A2B, DEEP,
       "deals",
       [scrape("costco-squishmallows-search",
              "https://www.costco.com/CatalogSearch?keyword=squishmallow")],
       ["restock", "back in stock", "exclusive", "plush"],
       "Squishmallow restocks — direct Costco.com watches.", price=800,
       channel="costco-squishmallows", geo_filter_enabled=True),
    _v("costco-pokemon", "Costco: Pokémon", "🔴", 0xE01A2B, DEEP, "deals",
       [scrape("costco-pokemon-search",
              "https://www.costco.com/CatalogSearch?keyword=pokemon+trading+cards")],
       ["restock", "back in stock", "pokemon", "tcg", "booster"],
       "Pokémon TCG restocks — direct Costco.com watches.", price=800,
       channel="costco-pokemon", geo_filter_enabled=True),
    # 🏪 DOLLAR GENERAL category (Kevin, 2026-07-27): "add a dollar
    # general category for pokemon." Real search endpoint is
    # `/product-search?q=<term>` — a bare `/search?q=` 404s (found via
    # the homepage's own search form action). Distinct from the older
    # "dollar-general" TRACKERS vertical above (Reddit/Slickdeals relay,
    # community shelf-sighting reports) — this is a direct site scrape,
    # same shape as Target/Best Buy/Sam's Club/Costco.
    _v("dollargeneral-pokemon", "Dollar General: Pokémon", "🏪", 0xFFCC00,
       DEEP, "deals",
       [scrape("dollargeneral-pokemon-search",
              "https://www.dollargeneral.com/product-search?q=pokemon")],
       ["restock", "back in stock", "pokemon", "tcg", "booster"],
       "Pokémon TCG restocks — direct DollarGeneral.com watches.", price=800,
       channel="dg-pokemon", geo_filter_enabled=True),
    # 🔷 BEST BUY category (Kevin, 2026-07-27): "add a whole best buy
    # category. We want parts, computers, devices, pokemon if they have
    # it, and consoles, and accessories, and whatever products we can
    # use or profit on." One channel per item type, each a real
    # `_parse_bestbuy` scrape (live-verified per search term the same
    # evening — every one of these returned real product data).
    _v("bestbuy-parts", "Best Buy: Parts", "🔷", 0x0A4EA2, DEEP, "deals",
       [scrape("bestbuy-parts-search",
              "https://www.bestbuy.com/site/searchpage.jsp?st=computer+parts")],
       ["restock", "back in stock", "gpu", "cpu", "motherboard", "ssd"],
       "GPUs, CPUs, and PC parts — direct BestBuy.com watches.", price=800,
       channel="parts"),
    _v("bestbuy-computers", "Best Buy: Computers", "🔷", 0x0A4EA2, DEEP, "deals",
       [scrape("bestbuy-computers-search",
              "https://www.bestbuy.com/site/searchpage.jsp?st=laptop")],
       ["restock", "back in stock", "laptop", "desktop"],
       "Laptops + desktops — direct BestBuy.com watches.", price=800,
       channel="computers"),
    _v("bestbuy-devices", "Best Buy: Devices", "🔷", 0x0A4EA2, DEEP, "deals",
       [scrape("bestbuy-devices-search",
              "https://www.bestbuy.com/site/searchpage.jsp?st=cell+phone")],
       ["restock", "back in stock", "phone", "tablet"],
       "Phones + tablets — direct BestBuy.com watches.", price=800,
       channel="devices"),
    _v("bestbuy-pokemon", "Best Buy: Pokémon", "🔷", 0x0A4EA2, DEEP, "deals",
       [scrape("bestbuy-pokemon-search",
              "https://www.bestbuy.com/site/searchpage.jsp?st=pokemon+trading+cards")],
       ["restock", "back in stock", "pokemon", "tcg", "booster"],
       "Pokémon TCG restocks — direct BestBuy.com watches.", price=800,
       channel="pokemon", geo_filter_enabled=True),
    _v("bestbuy-consoles", "Best Buy: Consoles", "🔷", 0x0A4EA2, DEEP, "deals",
       [scrape("bestbuy-consoles-search",
              "https://www.bestbuy.com/site/searchpage.jsp?st=gaming+console")],
       ["restock", "back in stock", "playstation", "xbox", "switch"],
       "Consoles + bundles — direct BestBuy.com watches.", price=800,
       channel="consoles"),
    _v("bestbuy-accessories", "Best Buy: Accessories", "🔷", 0x0A4EA2, DEEP, "deals",
       [scrape("bestbuy-accessories-search",
              "https://www.bestbuy.com/site/searchpage.jsp?st=tech+accessories")],
       ["restock", "back in stock", "case", "charger", "cable"],
       "Cases, chargers, and tech accessories — direct BestBuy.com watches.",
       price=800, channel="tech-accessories"),

    # 🎮 WARFRAME category (warframe-flip-d, Kevin 2026-07-27): "Well I
    # wanted a whole warframe category, with channels for item types" —
    # its own category, one channel per item type, each with its own
    # independent scan of the real, official, no-auth warframe.market
    # API (verified live: sets, rare/vaulted relics, arcanes, and riven
    # auctions all confirmed reachable and shaped as designed). See
    # WarframeFlipFetcher (fetchers.py) + warframe_market.py's strategies
    # (direct arbitrage, lowball, set-vs-parts, riven peer-comparison).
    # DEEP, not STAR — same as desktops/servers under COMPUTERS: still
    # gets a real, always-on channel via the WARFRAME category (that's
    # the whole ask), just doesn't crowd the Hub's front-row row (kept
    # deliberately small, 5-15 verticals, for that surface specifically).
    _v("warframe-sets", "Prime Sets", "🎮", 0x1B9CFC, DEEP, "deals",
       [warframe_flip("set")],
       ["flip", "arbitrage", "prime set", "set-vs-parts"],
       "Prime Set flips — buy the parts, sell the assembled set, or "
       "catch a real price gap, with real in-game trader names.",
       price=800, channel="sets"),
    _v("warframe-relics", "Relics", "🎮", 0x1B9CFC, DEEP, "deals",
       [warframe_flip("relic")],
       ["flip", "arbitrage", "relic", "vaulted", "radiant"],
       "Rare (vaulted) relic flips, ranked by real live orders.",
       price=800, channel="relics"),
    # warframe-arcane-ranks-d (Kevin, 2026-07-27): "I want rank 0
    # arcanes channel and a rank 5 arcanes channel. So we keep the cheap
    # arcanes and expensive deals separate" → "3 channel. Rank 0 flips,
    # mid flips, and rank 5 flips" — replaces the single lumped Arcanes
    # channel with 3 rank-scoped ones, no overlap.
    _v("warframe-arcanes-rank0", "Arcanes (Rank 0)", "🎮", 0x1B9CFC, DEEP,
       "deals", [warframe_flip("arcane-rank0")],
       ["flip", "arbitrage", "arcane", "rank 0", "cheap"],
       "Rank 0 Arcane Enhancement flips — the cheap tier, on its own.",
       price=800, channel="arcanes-rank0"),
    _v("warframe-arcanes-mid", "Arcanes (Rank 1-4)", "🎮", 0x1B9CFC, DEEP,
       "deals", [warframe_flip("arcane-mid")],
       ["flip", "arbitrage", "arcane", "rank"],
       "Rank 1-4 Arcane Enhancement flips.",
       price=800, channel="arcanes-mid"),
    _v("warframe-arcanes-rank5", "Arcanes (Rank 5)", "🎮", 0x1B9CFC, DEEP,
       "deals", [warframe_flip("arcane-rank5")],
       ["flip", "arbitrage", "arcane", "rank 5", "max rank", "expensive"],
       "Rank 5 (max) Arcane Enhancement flips — the expensive tier, on "
       "its own.",
       price=800, channel="arcanes-rank5"),
    _v("warframe-rivens", "Riven Mods", "🎮", 0x1B9CFC, DEEP, "deals",
       [warframe_flip("riven")],
       ["flip", "riven", "disposition", "roll"],
       "Riven Mod flips — underpriced rolls vs. their own real peers, "
       "weighted by weapon disposition.",
       price=800, channel="rivens"),
    # warframe-misc-d (Kevin, 2026-07-27): "add legendary core flips too
    # or a miscellaneous category" — a real, extensible bucket for
    # single-fungible-SKU Warframe items beyond sets/relics/arcanes/
    # rivens. Live-verified: only Legendary + Ancient Fusion Core carry
    # the matching "fusion core" tag today — a genuine, if narrow, start.
    _v("warframe-misc", "Misc (Legendary Cores)", "🎮", 0x1B9CFC, DEEP,
       "deals", [warframe_flip("misc")],
       ["flip", "arbitrage", "legendary core", "fusion core"],
       "Legendary/Ancient Fusion Core flips + any other single-item "
       "Warframe trade that doesn't fit sets/relics/arcanes/rivens.",
       price=800, channel="misc"),
    # jackpot-d (Kevin, 2026-07-27): "add a opportunities of a life time
    # channel incase some crazy deal or opportunity arises." One
    # combined sweep across EVERY item type, hardened with multiple
    # confirming signals (WarframeFlipFetcher._is_jackpot: a real live
    # buyer AND a high absolute profit floor AND a strong profit ratio —
    # never noise from either signal alone).
    _v("warframe-jackpot", "🎰 Opportunity of a Lifetime", "🎮", 0xFFD700,
       DEEP, "deals", [warframe_flip("jackpot")],
       ["flip", "jackpot", "crazy deal", "huge profit"],
       "Rare, hardened-filter finds across EVERY Warframe item type — "
       "real buyer, big profit, big ratio, all at once.",
       price=800, channel="jackpot"),
    # 🏠 REAL ESTATE category (Kevin, 2026-07-28/29): deal-sourcing
    # for off-market/motivated-seller leads, split by property type.
    # v1 deliberately uses only free, low-legal-risk sources — real
    # estate/wholesaling subreddits (same OAuth fetcher + is_actionable
    # noise filter already proven for #222/#224) — NOT Zillow/Redfin/
    # Realtor.com scraping (stealth_browser.py self-documents it can't
    # reliably clear that tier of WAF, and MLS/Zillow ToS + CFAA
    # exposure has no existing precedent here). County/HUD/USDA public
    # open-data feeds are a free follow-up once Kevin names his target
    # county's real portal URL.
    _v("realestate-single-family", "Real Estate: Single-Family", "🏠",
       0x8B5E3C, DEEP, "local",
       [reddit_sub("realestateinvesting"),
        reddit_search("realestateinvesting", "single family motivated seller"),
        reddit_search("Wholesaling", "single family"),
        # county-records-d (Kevin, 2026-08-01): real county court
        # listings, Christian Co KY + Montgomery Co TN -- verified-live
        # HTML, not guessed. Reddit ruled out (Kevin banned).
        scrape("realestate-christian-county-ky",
               "https://christiancountymastercommissioner.com/listings/"),
        scrape("realestate-montgomery-county-tn",
               "https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales"),
        # edmonson-county-d (Kevin, 2026-08-01): 3rd county source,
        # same real-record pattern -- server-rendered, confirmed live.
        scrape("realestate-edmonson-county-ky",
               "https://www.edmonsoncountymastercommissioner.com/sale-dates.html")],
       ["motivated seller", "must sell", "as-is", "pre-foreclosure",
        "inherited", "wholesale"],
       "Off-market single-family leads — motivated-seller and wholesale "
       "signals from real-estate investing communities.",
       price=800, channel="single-family"),
    _v("realestate-condos", "Real Estate: Condos", "🏠", 0x8B5E3C, DEEP,
       "local",
       [reddit_search("realestateinvesting", "condo"),
        reddit_search("RealEstate", "condo motivated seller")],
       ["condo", "hoa", "motivated seller", "must sell"],
       "Condo leads — motivated-seller signals from real-estate "
       "communities.",
       price=800, channel="condos"),
    # lien-auction-d (Kevin, 2026-08-01): tax LIEN certificate sale
    # announcements (buying the lien, not the property) -- a
    # deliberately SEPARATE, non-"realestate-"-prefixed slug so it
    # bypasses runtime.py's buy-box gate entirely (a sale-date
    # announcement has no price/location to filter on). Still lives
    # in the REAL ESTATE category via CATEGORY_SLUGS below.
    _v("liens-christian-county", "Christian Co. KY Tax Lien Sale", "🔔",
       0x8B5E3C, DEEP, "local",
       [scrape("christian-co-tax-sale-date",
               "https://christiancountyky.gov/tax-sale-date")],
       ["tax lien", "delinquent tax", "certificate of delinquency"],
       "Christian County, KY delinquent property tax sale date + "
       "registration deadline — a seasonal check (weekly), not a "
       "continuous poll; this content changes at most once a year.",
       price=800, channel="lien-auctions"),
    _v("realestate-apartments", "Real Estate: Apartments", "🏠", 0x8B5E3C,
       DEEP, "local",
       [reddit_sub("Landlord"),
        reddit_search("realestateinvesting", "multifamily"),
        reddit_search("realestateinvesting", "apartment building")],
       ["multifamily", "apartment", "duplex", "triplex", "fourplex",
        "motivated seller"],
       "Apartment/multifamily leads — duplex through larger multifamily, "
       "motivated-seller signals from real-estate communities.",
       price=800, channel="apartments"),
    # income-securing-d (Kevin, 2026-08-01): "income securing
    # category... loans, grants, and other stuff" (clarified: loans +
    # grants + incentive programs together). Live tracker for the
    # grants half via the real grants.gov API (curl-verified
    # 2026-08-01, no auth needed); the loan/SBA half is a curated
    # static reference (business_funding_directory.py) surfaced via
    # /funding, not a live poll — loan offers aren't "new listings."
    _v("business-grants", "Business Grants (grants.gov)", "💰",
       0x2E8B57, DEEP, "online",
       [("grants-gov-small-business",
         "https://api.grants.gov/v1/api/search2?keyword=small+business"
         "&oppStatuses=forecasted%7Cposted&postedDays=14", "grants-gov")],
       ["grant", "funding opportunity", "sba", "small business"],
       "Federal grant opportunities relevant to small business, "
       "polled from grants.gov's real public API (posted in the last "
       "14 days) — see also /funding for SBA loans + lender reference.",
       price=800, channel="business-grants"),
]

# ── focus (Kevin, 2026-08-03) ───────────────────────────────────────────
# "Everything goes except for Warframe and OSRS... and mead. I want the
# discord to feel light but powerful. Not too large."
#
# Written as a KEEP list rather than a retire list, deliberately: the
# catalog below is where new ideas land, and a retire-list quietly lets
# every one of them go live by default. That default is how the shop got to
# 88 verticals of which SIX had delivered anything in 72 hours, and how
# #mead-deals ended up advertising hotdogs. Adding a vertical to the file
# is now a draft; adding it here is the decision to ship it.
#
# Nothing is deleted — everything stays defined below as history, and a
# tracker comes back the moment its slug is listed here.
KEEP_PREFIXES: tuple[str, ...] = (
    "warframe-",     # WARFRAME — warframe.market, official + no-auth
    "osrs-",         # OLD SCHOOL RUNESCAPE — prices.runescape.wiki
)
KEEP_SLUGS: frozenset[str] = frozenset({
    "mead-brewing",  # MEAD LOUNGE — its own age-gated category
})


def _is_live(v: "Vertical") -> bool:
    return v.slug.startswith(KEEP_PREFIXES) or v.slug in KEEP_SLUGS


ALL_VERTICALS: list[Vertical] = CATALOG          # every definition, incl. retired
CATALOG = [v for v in CATALOG if _is_live(v)]
RETIRED_SLUGS: frozenset[str] = frozenset(
    v.slug for v in ALL_VERTICALS if not _is_live(v))

CATALOG_BY_SLUG = {v.slug: v for v in CATALOG}


def star_verticals() -> list[Vertical]:
    return [v for v in CATALOG if v.tier == STAR]


def deep_verticals() -> list[Vertical]:
    return [v for v in CATALOG if v.tier == DEEP]


def get_vertical(slug: str) -> Vertical | None:
    return CATALOG_BY_SLUG.get(slug)


def set_tracker_enabled(data_dir, slug: str, enabled: bool) -> tuple[bool, str]:
    """Owner on/off toggle for one tracker vertical (Kevin, 2026-07-25:
    "a way for me to turn channels on and maybe turn some channels
    off?"). Resolves slug -> its BotProject (created by `sov scout
    sync`) and flips status to live/paused — BotManager.load() already
    skips paused projects, so this is a real, immediate switch: no more
    polling or Discord posts from it until it's turned back on."""
    from sovereign_agent import bot_projects

    v = CATALOG_BY_SLUG.get(slug)
    if v is None:
        return False, f"no tracker vertical named {slug!r}"
    p = bot_projects.load(v.project, data_dir)
    if p is None:
        return False, f"{v.name} hasn't been synced yet — run `sov scout sync` first"
    p.status = "live" if enabled else "paused"
    bot_projects.save(p, data_dir)
    verb = "resumed" if enabled else "paused"
    return True, f"{v.emoji} {v.name} tracker {verb}"


# gaming-d: the 🎮 GAMING category set, in display order — consoles
# (hardware) first, then games. Each lives in its OWN channel (v.channel).
GAMING_SLUGS: list[str] = [
    "retro-consoles", "consoles",          # ── consoles (hardware) ──
    "retro-games", "gamedeals", "freegames",  # ── games (separate) ──
]


# categories-d (Kevin, 2026-07-18): every named Discord category, as data —
# category → its verticals in display order. Each listed vertical OWNS a
# clean channel (v.channel, no "track-" prefix). Adding a category = one
# entry here; the blueprint, guides, and webhook specs all follow.
CATEGORY_SLUGS: dict[str, list[str]] = {
    # focus-d (Kevin, 2026-08-03): gaming + mead only. Every other category
    # retired with its verticals — see KEEP_PREFIXES/KEEP_SLUGS above.
    "WARFRAME": ["warframe-sets", "warframe-relics", "warframe-arcanes-rank0",
                 "warframe-arcanes-mid", "warframe-arcanes-rank5",
                 "warframe-rivens", "warframe-misc", "warframe-jackpot"],
    "OLD SCHOOL RUNESCAPE": ["osrs-starter", "osrs-mid", "osrs-high",
                             "osrs-volume"],
    # mead-lock-d: homed so it isn't an orphan tracker. NOT in
    # SUBSCRIBABLE_CATEGORIES on purpose — /mead-access + the Mead-Head role
    # is the 21+ gate, and a /my-panel toggle would skip that attestation.
    "MEAD LOUNGE": ["mead-brewing"],
}


def gaming_verticals() -> list[Vertical]:
    """The verticals that belong in the 🎮 GAMING category (ordered)."""
    return category_verticals("GAMING")


def category_verticals(category: str) -> list[Vertical]:
    """A named category's verticals, in display order."""
    return [CATALOG_BY_SLUG[s] for s in CATEGORY_SLUGS.get(category, ())
            if s in CATALOG_BY_SLUG]


def homed_slugs() -> set[str]:
    """Every slug that lives in a named category (has its own clean
    channel there) — excluded from the generic TRACKERS row."""
    return {s for slugs in CATEGORY_SLUGS.values() for s in slugs}


def channeled_verticals() -> list[Vertical]:
    """Every vertical that owns a named channel: the ★ stars (TRACKERS
    row) + every category-homed vertical — ordered, deduped by slug.
    This is the one list guides + webhook specs iterate."""
    out: list[Vertical] = []
    seen: set[str] = set()
    for v in star_verticals():
        if v.slug not in seen:
            seen.add(v.slug)
            out.append(v)
    for slugs in CATEGORY_SLUGS.values():
        for s in slugs:
            v = CATALOG_BY_SLUG.get(s)
            if v is not None and v.slug not in seen:
                seen.add(v.slug)
                out.append(v)
    return out


# my-panel-d (Kevin, 2026-07-26): "a per user control panel... with buttons
# to subscribe to each category." The one grouping every category-level
# bulk-subscribe UI reads from — TRACKERS (the star verticals that DIDN'T
# get a named home) plus the 6 named categories. Order matters: it's the
# button row order in the Discord panel.
SUBSCRIBABLE_CATEGORIES: tuple[str, ...] = (
    # NOTE: this tuple is SEPARATE from CATEGORY_SLUGS — a category added
    # there gets Discord channels but stays invisible in /my-panel until
    # it's listed here too. That's exactly how OSRS first shipped with
    # working channels nobody could subscribe to.
    #
    # focus-d (Kevin, 2026-08-03): gaming only. MEAD LOUNGE is deliberately
    # absent — /mead-access + the Mead-Head role is the 21+ gate, and a
    # panel toggle would hand out access without that attestation.
    # reorg-d (Kevin, 2026-08-03): TRACKERS dropped — it synthesized the
    # star verticals with no named home, and after the focus cut there are
    # none, so it rendered as an empty group in /my-panel.
    "WARFRAME", "OLD SCHOOL RUNESCAPE",
)

# panel-d (Kevin, 2026-08-04): "shorten the name of Old School Runescape to
# OSRS inside /my-panel because it is too long and cuts off or overflows."
#
# DISPLAY ONLY. The value here is never an identity: the picker option's
# `value` and the fine-tune select's custom_id both still carry the REAL
# category name. Swapping those too would silently break every handler that
# matches on it — the same class of bug as the [1:] slice.
PANEL_LABELS: dict[str, str] = {
    "OLD SCHOOL RUNESCAPE": "OSRS",
}


def panel_label(category: str) -> str:
    """Short name for a cramped Discord dropdown row."""
    return PANEL_LABELS.get(category, category)


def subscribable_categories() -> dict[str, list[Vertical]]:
    """Every category with real per-vertical subscribe roles, in panel
    display order. TRACKERS is synthesized the same way blueprint.py's
    `_tracker_channels()` builds it (★ stars minus the ones homed
    elsewhere) — kept as ONE definition so the panel can never drift
    from what the blueprint actually provisioned roles for."""
    # reorg-d (Kevin, 2026-08-03): this used to hardcode TRACKERS at index 0
    # and iterate SUBSCRIBABLE_CATEGORIES[1:]. The moment TRACKERS was
    # dropped from that tuple, the slice silently ate WARFRAME instead —
    # /my-panel showed OSRS alone and Warframe became unsubscribable with no
    # error anywhere. Driven by NAME now, so the tuple's order and contents
    # are free to change.
    homed = homed_slugs()
    out: dict[str, list[Vertical]] = {}
    # panel-d (Kevin, 2026-08-04): "add the python and ai systems to my
    # panel." The code-school tracks aren't Verticals, but they expose the
    # same five attributes the panel reads (ping_role / emoji / name / slug /
    # blurb), so they slot straight in. Appended last: learning is what he
    # opted into most recently, and the trackers are the paid product.
    try:
        from sovereign_agent.code_school.tracks import enabled_tracks
        school = {tr.name: [tr] for tr in enabled_tracks()}
    except Exception:  # noqa: BLE001 — the panel must open regardless
        school = {}
    for cat in SUBSCRIBABLE_CATEGORIES:
        if cat == "TRACKERS":
            # synthesized exactly like blueprint._tracker_channels(): the ★
            # stars with no named home. Empty once everything is homed, and
            # an empty group is dropped rather than rendered as a dead row.
            verts = [v for v in star_verticals() if v.slug not in homed]
        else:
            verts = category_verticals(cat)
        if verts:
            out[cat] = verts
    out.update(school)
    return out


def bulk_toggle_roles(verts: list[Vertical],
                      member_role_names: set[str]) -> tuple[str, list[str]]:
    """Category bulk-toggle logic — pure, no discord.py dependency, so the
    Discord command layer stays thin wiring over a tested decision.

    If the member already holds EVERY vertical's role in this category,
    tapping the category button means "unsubscribe from all of them."
    Otherwise it means "subscribe to whichever ones I'm still missing" —
    never re-adds roles already held. Returns (action, role_names)."""
    if not verts:
        return "subscribe", []
    have = [v for v in verts if v.ping_role in member_role_names]
    if len(have) == len(verts):
        return "unsubscribe", [v.ping_role for v in verts]
    missing = [v.ping_role for v in verts if v.ping_role not in member_role_names]
    return "subscribe", missing


def select_diff_roles(verts: list[Vertical], member_role_names: set[str],
                      selected_slugs) -> tuple[list[str], list[str]]:
    """Per-vertical select-menu diff — pure. Given the exact set of slugs
    the member just checked in the dropdown, returns (roles_to_add,
    roles_to_remove) so the caller applies exactly that membership,
    nothing more and nothing left stale."""
    selected = set(selected_slugs or ())
    add = [v.ping_role for v in verts
          if v.slug in selected and v.ping_role not in member_role_names]
    remove = [v.ping_role for v in verts
             if v.slug not in selected and v.ping_role in member_role_names]
    return add, remove


__all__ = ["Vertical", "CATALOG", "CATALOG_BY_SLUG", "STAR", "DEEP",
           "COMMON_EXCLUDES", "slickdeals", "reddit_sub", "reddit_search",
           "star_verticals", "deep_verticals", "get_vertical",
           "GAMING_SLUGS", "gaming_verticals", "CATEGORY_SLUGS",
           "category_verticals", "homed_slugs", "channeled_verticals",
           "SUBSCRIBABLE_CATEGORIES", "subscribable_categories",
           "bulk_toggle_roles", "select_diff_roles",
           "set_tracker_enabled"]
