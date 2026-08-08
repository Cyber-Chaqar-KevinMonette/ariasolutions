"""shop — the Bot Shop catalog: sellable products, tiers, and prices.

Turns the live bot runtime into an income surface. A `Product` is one thing
for sale — a subscription tier or a per-bot plan — carrying its Stripe
Payment Link URL (Stripe handles all recurring billing; we only store the
link, never a secret). Each product is tagged **attended** or not:

  • attended=False → an AUTONOMOUS bot (runs on the fleet daemon, no LLM,
    keeps delivering 24/7 even when Aria sleeps). "Your alerts never sleep."
  • attended=True  → a WITH-HER feature (conversational / ask-Aria) that only
    works while she's awake (see presence.py).

Storage: one JSON file per product under `<data>/shop/`, atomic + fsync,
corrupt-file-resilient, path-safe slugs. Same durable pattern as
`bot_projects.py` / `cockpit/user_themes.py` — pure model + thin file I/O.
The runtime that fulfils an order is the existing `discord_runtime`; this is
only the catalog + pricing.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "Product",
    "BILLING_KINDS",
    "TIERS",
    "slugify",
    "validate",
    "save",
    "load",
    "list_all",
    "delete",
    "shop_dir",
    "money",
    "is_shop_query",
    "compose_shop_report",
    "seed_starter_catalog",
    "seed_tracker_products",
    "seed_pass_products",
    "storefront_embeds",
    "publish_storefront",
    "publish_buy_links",
]

# billing cadence for a product's recurring/one-time price
BILLING_KINDS: list[tuple[str, str]] = [
    ("monthly", "Monthly subscription"),
    ("yearly", "Yearly subscription"),
    ("one_time", "One-time purchase"),
]
_BILLING_KEYS = {k for k, _ in BILLING_KINDS}

# starting subscription tiers (Kevin tweaks freely). tier "" == not a tier.
TIERS: list[tuple[str, str]] = [
    ("", "— (per-bot / no tier)"),
    ("basic", "Basic"),
    ("pro", "Pro"),
    ("vip", "VIP"),
]
_TIER_KEYS = {k for k, _ in TIERS}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _./+()-]{0,60}$")


@dataclass
class Product:
    """One sellable item in the shop."""
    name: str
    blurb: str = ""
    kind: str = "notification-feed"     # mirrors bot_projects BOT_KINDS (or a tier)
    tier: str = ""                       # "", basic, pro, vip
    billing: str = "monthly"             # monthly | yearly | one_time
    price_cents: int = 0                 # the headline price in cents
    setup_cents: int = 0                 # optional one-time setup fee (0 = none)
    stripe_url: str = ""                 # Stripe Payment Link (never a secret)
    access_role: str = ""                # Discord role granted on purchase
    attended: bool = False               # True = needs Aria awake; False = autonomous
    active: bool = True                  # listed in the published storefront?
    sort: int = 100                      # ascending display order
    # passes-d (Kevin, 2026-07-26): "24 hour pass... week pass, month pass,
    # year pass." Display/reference only — the actual entitlement grant is
    # driven by stripe_sync.PASS_PLANS (price-cents keyed, robust to product
    # renames, same philosophy as AMOUNT_PLAN). 0 = not a time-boxed pass.
    duration_days: int = 0
    created_at: str = ""
    modified_at: str = ""

    @property
    def runs_without_her(self) -> bool:
        return not self.attended

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Product":
        data = json.loads(text)
        known = {f for f in Product(name="x").as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})

    def price_label(self) -> str:
        head = money(self.price_cents)
        cadence = {"monthly": "/mo", "yearly": "/yr", "one_time": ""}.get(self.billing, "")
        if not cadence and self.duration_days:
            cadence = f" / {_duration_label(self.duration_days)}"
        label = f"{head}{cadence}"
        if self.setup_cents:
            label = f"{money(self.setup_cents)} setup + {label}"
        return label


def money(cents: int) -> str:
    """cents → $X or $X.YY (no trailing .00)."""
    dollars = (cents or 0) / 100
    return f"${dollars:.0f}" if dollars == int(dollars) else f"${dollars:.2f}"


def _duration_label(days: int) -> str:
    """A one-time pass's duration, in the most natural unit: 1 → '24 hours',
    7 → 'week', 30 → 'month', 365 → 'year', else 'Nd'."""
    if days == 1:
        return "24 hours"
    if days == 7:
        return "week"
    if days == 30:
        return "month"
    if days == 365:
        return "year"
    return f"{days}d"


def slugify(name: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (name or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s[:48] or "product"


def validate(p: Product) -> list[str]:
    errs: list[str] = []
    if not (p.name or "").strip():
        errs.append("product name is required")
    elif not _NAME_RE.match(p.name.strip()):
        errs.append("product name has invalid characters")
    if p.billing not in _BILLING_KEYS:
        errs.append(f"billing {p.billing!r} not one of {sorted(_BILLING_KEYS)}")
    if p.tier not in _TIER_KEYS:
        errs.append(f"tier {p.tier!r} not one of {sorted(_TIER_KEYS)}")
    if (p.price_cents or 0) < 0 or (p.setup_cents or 0) < 0:
        errs.append("prices cannot be negative")
    if (p.duration_days or 0) < 0:
        errs.append("duration_days cannot be negative")
    if p.stripe_url and not p.stripe_url.startswith(("https://", "http://")):
        errs.append("stripe_url must be a full https:// link")
    return errs


def shop_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "shop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(data_dir: Path, name: str) -> Path:
    return shop_dir(data_dir) / f"{slugify(name)}.json"


def save(p: Product, data_dir: Path) -> Path:
    errs = validate(p)
    if errs:
        raise ValueError("product invalid:\n  - " + "\n  - ".join(errs))
    now = datetime.now(timezone.utc).isoformat()
    if not p.created_at:
        p.created_at = now
    p.modified_at = now
    path = _path(data_dir, p.name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(p.to_json(), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def load(name: str, data_dir: Path) -> Product | None:
    path = _path(data_dir, name)
    if not path.is_file():
        return None
    try:
        return Product.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_all(data_dir: Path, *, only_active: bool = False) -> list[Product]:
    out: list[Product] = []
    for f in sorted(shop_dir(data_dir).glob("*.json")):
        try:
            p = Product.from_json(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — skip a corrupt file, never crash the list
            continue
        if only_active and not p.active:
            continue
        out.append(p)
    out.sort(key=lambda x: (x.sort, x.name.lower()))
    return out


def delete(name: str, data_dir: Path) -> bool:
    path = _path(data_dir, name)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ── chat bridge: "what's in the shop?" ───────────────────────────────────
_SHOP_TRIGGERS = (
    "what's in the shop", "whats in the shop", "what are we selling",
    "shop catalog", "the catalog", "our prices", "what do we sell",
    "shop menu", "our shop", "the shop",
)


def is_shop_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _SHOP_TRIGGERS)


def compose_shop_report(data_dir: Path | None = None) -> str:
    """Deterministic, grounded answer from the real catalog — never invented."""
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return "The shop isn't set up yet. Open the Shop Studio (/shop) to add products."
    products = list_all(data_dir, only_active=True)
    if not products:
        return ("The shop is empty so far — open the Shop Studio (/shop) to add "
                "products (tiers, per-bot plans, Stripe links).")
    lines = [f"🛒 Our shop — {len(products)} "
             f"product{'s' if len(products) != 1 else ''}:"]
    for p in products:
        mode = "🌙 autonomous" if p.runs_without_her else "🔆 with-Aria"
        tier = f" · {p.tier}" if p.tier else ""
        lines.append(f"  • [b]{p.name}[/b] — {p.price_label()}{tier} ({mode})"
                     + (f" — {p.blurb}" if p.blurb else ""))
    return "\n".join(lines)


def storefront_embeds(products: list[Product]) -> list[dict]:
    """One Discord embed per active product — ALL of them (chunking to
    Discord's 10-embeds-per-message cap happens at publish time; the old
    [:10] truncation silently dropped Custom Bot the day the catalog hit
    10 products + the stats card). A product with a stripe_url becomes a
    clickable 'Subscribe' title."""
    active = [p for p in products if p.active]
    out: list[dict] = []
    for p in active:
        mode = "🌙 Autonomous — runs 24/7, even when Aria sleeps" if p.runs_without_her \
            else "🔆 With-Aria — live when she's awake"
        desc = (p.blurb + "\n\n" if p.blurb else "") + f"**{p.price_label()}**\n{mode}"
        emb: dict = {"title": p.name, "description": desc,
                     "color": 0x22D3EE if p.runs_without_her else 0xA78BFA}
        if p.stripe_url:
            emb["url"] = p.stripe_url
        if p.tier:
            emb.setdefault("footer", {"text": f"{p.tier.upper()} tier"})
        out.append(emb)
    return out


def publish_storefront(data_dir: Path, *, live: bool = False,
                       webhook_env: str = "DISCORD_SHOP_WEBHOOK_URL",
                       fallback_env: str = "DISCORD_WEBHOOK_URL",
                       include_stats: bool = True):
    """Publish the active catalog (+ optional public stats) to the shop channel
    via the webhook. Dry-run unless `live` and a webhook resolves. Returns a
    DeliveryResult."""
    products = list_all(data_dir, only_active=True)
    embeds = storefront_embeds(products)
    if include_stats:
        try:
            from sovereign_agent.shop_stats import aggregate_stats, public_stats_embed
            embeds = [public_stats_embed(aggregate_stats(data_dir))] + embeds
        except Exception:  # noqa: BLE001
            pass
    env = webhook_env if (os.environ.get(webhook_env) or "").strip() else fallback_env
    from sovereign_agent.discord_runtime.delivery import WebhookDelivery
    header = "🛒 **BigKev's Bot Shop** — reliable, managed Discord bots."
    # Discord caps 10 embeds AND 6000 embed-chars per MESSAGE, not per
    # catalog — chunk into as many messages as needed (missing-product-d:
    # the old single-message [:10] cut dropped the 11th card, Custom Bot).
    # Header rides the first message only.
    from sovereign_agent.discord_limits import chunk_embeds
    delivery = WebhookDelivery(env, live=live)
    result = None
    for i, chunk in enumerate(chunk_embeds(embeds) or [[]]):
        result = delivery.send(header if i == 0 else "", embeds=chunk,
                               username="BigKev's Bot Shop")
        if live and not result.sent:
            return result          # report the failure, don't keep spraying
    return result


def publish_buy_links(data_dir: Path, *, live: bool = False,
                      webhook_env: str = "DISCORD_BUYLINKS_WEBHOOK_URL",
                      fallback_env: str = "DISCORD_WEBHOOK_URL"):
    """passes-d (Kevin, 2026-07-26): "channels for direct purchase links."
    The plain, non-personalized Payment Link per active product — a
    quick-browse alternative to /buy or /passes (which personalize the
    link so the purchase auto-attributes). Same embed/chunk/dry-run
    machinery as publish_storefront, just a different header + channel
    and no stats card (this is a link list, not the storefront pitch)."""
    products = list_all(data_dir, only_active=True)
    embeds = storefront_embeds(products)
    env = webhook_env if (os.environ.get(webhook_env) or "").strip() else fallback_env
    from sovereign_agent.discord_runtime.delivery import WebhookDelivery
    header = ("🔗 **Direct purchase links** — /buy or /passes give you a "
             "personalized link instead (auto-confirms your purchase).")
    from sovereign_agent.discord_limits import chunk_embeds
    delivery = WebhookDelivery(env, live=live)
    result = None
    for i, chunk in enumerate(chunk_embeds(embeds) or [[]]):
        result = delivery.send(header if i == 0 else "", embeds=chunk,
                               username="BigKev's Bot Shop")
        if live and not result.sent:
            return result
    return result


def seed_starter_catalog(data_dir: Path) -> list[Product]:
    """Write Kevin's starting tiers + a couple of per-bot plans (idempotent —
    skips any product name that already exists). Numbers are starting points."""
    starters = [
        # ── managed-hosting TIERS (recurring monthly) ──
        Product(name="Basic", blurb="1 bot, 1 source, reliable 24/7 delivery.",
                kind="analytics-stats", tier="basic", billing="monthly",
                price_cents=500, access_role="Subscriber-Basic", attended=False, sort=10),
        Product(name="Pro", blurb="Up to 3 bots/sources, priority delivery, #priority-support.",
                kind="analytics-stats", tier="pro", billing="monthly",
                price_cents=1200, access_role="Subscriber-Pro", attended=False, sort=20),
        Product(name="VIP", blurb="Custom bots, private channel, early access, ask-Aria.",
                kind="analytics-stats", tier="vip", billing="monthly",
                price_cents=2500, access_role="Subscriber-VIP", attended=True, sort=30),
        # ── per-bot MONTHLY plans (recurring + one-time setup) ──
        Product(name="Restock Alert Bot", blurb="Pings your channel the moment stock returns.",
                kind="restock-alert", billing="monthly", price_cents=800,
                setup_cents=3000, attended=False, sort=110),
        Product(name="News / Release Feed Bot", blurb="RSS/API feed delivered as it drops.",
                kind="notification-feed", billing="monthly", price_cents=600,
                setup_cents=2500, attended=False, sort=120),
        Product(name="Sports Score Bot", blurb="Live scores + final results for your teams.",
                kind="notification-feed", billing="monthly", price_cents=800,
                setup_cents=3000, attended=False, sort=130),
        Product(name="Reminder / Schedule Bot", blurb="Scheduled reminders + recurring pings.",
                kind="reminder-schedule", billing="monthly", price_cents=500,
                setup_cents=2000, attended=False, sort=140),
        # ── ONE-TIME purchases (no recurring) ──
        Product(name="Welcome / Onboarding Bot", blurb="Greets + onboards new members.",
                kind="welcome-onboard", billing="one_time", price_cents=2000,
                attended=False, sort=210),
        Product(name="Reaction-Role Bot", blurb="Self-serve roles via reactions.",
                kind="role-reaction", billing="one_time", price_cents=2000,
                attended=False, sort=220),
        Product(name="Custom Bot (VIP build)", blurb="Bespoke bot built to spec + managed.",
                kind="other", billing="monthly", price_cents=1500,
                setup_cents=7500, access_role="Subscriber-VIP", attended=True, sort=230),
    ]
    written: list[Product] = []
    for p in starters:
        if load(p.name, data_dir) is None:
            save(p, data_dir)
            written.append(p)
    return written


def seed_tracker_products(data_dir: Path) -> list[Product]:
    """verticals-d (Kevin's pick: per-bot + all-access). One product per ★
    tracker vertical + a single all-access 'Scout Pass'. Idempotent."""
    import unicodedata
    from sovereign_agent.verticals import star_verticals

    def _safe(name: str) -> str:
        # product names allow [A-Za-z0-9 _./+()-]; fold accents, drop the rest
        folded = unicodedata.normalize("NFKD", name).encode(
            "ascii", "ignore").decode()
        return "".join(c for c in folded
                       if c.isalnum() or c in " _./+()-").strip() or "Tracker"

    written: list[Product] = []
    prods = [Product(
        name=f"{_safe(v.name)} Tracker",
        blurb=f"{v.blurb} Full-speed alerts filtered to what YOU chase, in "
              "your own feed.",
        kind="notification-feed", billing="monthly",
        price_cents=v.price_cents, access_role=f"Track-{v.slug}",
        attended=False, sort=300 + i)
        for i, v in enumerate(star_verticals())]
    prods.append(Product(
        name="Scout Pass All-Access",
        blurb="Every tracker, all niches, full-speed + personal filters — "
              "cards, sneakers, LEGO, GPUs, consoles, deals & more in one "
              "pass. The whole radar.",
        kind="notification-feed", billing="monthly",
        price_cents=1800, access_role="Scout-Pass", attended=False, sort=299))
    for p in prods:
        if load(p.name, data_dir) is None:
            save(p, data_dir)
            written.append(p)
    return written


def seed_pass_products(data_dir: Path) -> list[Product]:
    """passes-d (Kevin, 2026-07-26): "24 hour pass... week pass, a month
    pass, and a year pass" — one shared all-access tier, sold by duration
    only (not crossed with Basic/Pro/VIP), each a ONE-TIME purchase with
    a fixed `duration_days`. `access_role="Pass-Holder"` is the single
    role that unlocks the same channels VIP/Basic/Pro already do (see
    blueprint.py's SUBSCRIBERS category) — the entitlement record's own
    `plan` field still distinguishes which pass someone holds. Idempotent
    — skips any product name that already exists. Prices are Kevin's
    starting point, easy to retune."""
    passes = [
        Product(name="24-Hour Pass", blurb="A full day of all-access — every "
               "tracker, every feature, no commitment.",
               kind="access-pass", billing="one_time", price_cents=300,
               duration_days=1, access_role="Pass-Holder", attended=True,
               sort=5),
        Product(name="Week Pass", blurb="Seven days of all-access — try "
               "everything before you commit to a month.",
               kind="access-pass", billing="one_time", price_cents=900,
               duration_days=7, access_role="Pass-Holder", attended=True,
               sort=6),
        Product(name="Month Pass", blurb="Thirty days of all-access, "
               "one-time — no recurring subscription.",
               kind="access-pass", billing="one_time", price_cents=1900,
               duration_days=30, access_role="Pass-Holder", attended=True,
               sort=7),
        Product(name="Year Pass", blurb="A full year of all-access — the "
               "best per-day value, for the most committed.",
               kind="access-pass", billing="one_time", price_cents=14900,
               duration_days=365, access_role="Pass-Holder", attended=True,
               sort=8),
    ]
    written: list[Product] = []
    for p in passes:
        if load(p.name, data_dir) is None:
            save(p, data_dir)
            written.append(p)
    return written
