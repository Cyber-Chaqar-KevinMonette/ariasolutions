"""fulfillment.py — 🚚🏪 the "where & how do I get it" brain (Kevin's ask).

"For each find: links, hours, location, pickup-only or delivery or both."
Deal/RSS titles almost always name the retailer ("$18 at Amazon", "@
Walmart", "| Microcenter"), so we can HONESTLY tell a member:
  • which retailer,
  • is it delivery, in-store, or both,
  • a store-locator link (their exact nearest store + its real hours),
  • typical chain hours (labeled as typical — never fabricated per-store),
  • the direct item link.

Honest boundary: LIVE per-store stock and a member's exact nearest-store
address/hours need retailer/Places API keys (deferred — the Best Buy API
path). Until then we give the retailer's fulfillment model + locator +
typical hours, which genuinely answers "drive, pickup, or delivered?"
"""
from __future__ import annotations

import re

# fulfillment badges
DELIVERY = "🚚 ships to you"
INSTORE = "🏪 in-store — drive to check"
BOTH = "🏪🚚 pickup or delivery"
ONLINE = "🌐 online only — ships"


# retailer → (display, default fulfillment, store-locator url, typical hours)
# ("" locator = online-only, no stores to find)
RETAILERS: list[tuple[tuple[str, ...], dict]] = [
    (("amazon", "woot", "amzn"),
     {"name": "Amazon", "fill": DELIVERY, "locator": "",
      "hours": "24/7 online · Prime often free ship"}),
    (("walmart",),
     {"name": "Walmart", "fill": BOTH,
      "locator": "https://www.walmart.com/store/finder",
      "hours": "most stores ~6a–11p"}),
    (("target",),
     {"name": "Target", "fill": BOTH,
      "locator": "https://www.target.com/store-locator/find-stores",
      "hours": "most stores ~8a–10p"}),
    (("best buy", "bestbuy"),
     {"name": "Best Buy", "fill": BOTH,
      "locator": "https://www.bestbuy.com/site/store-locator",
      "hours": "most stores ~10a–8p"}),
    (("micro center", "microcenter"),
     {"name": "Micro Center", "fill": BOTH,
      "locator": "https://www.microcenter.com/site/stores/default.aspx",
      "hours": "most stores ~10a–9p · few locations, call ahead"}),
    (("gamestop",),
     {"name": "GameStop", "fill": BOTH,
      "locator": "https://www.gamestop.com/stores/",
      "hours": "most stores ~11a–7p"}),
    (("costco",),
     {"name": "Costco", "fill": BOTH,
      "locator": "https://www.costco.com/warehouse-locations",
      "hours": "~10a–8:30p · membership"}),
    (("sam's club", "sams club", "samsclub"),
     {"name": "Sam's Club", "fill": BOTH,
      "locator": "https://www.samsclub.com/club-finder",
      "hours": "~10a–8p · membership"}),
    (("home depot", "homedepot"),
     {"name": "Home Depot", "fill": BOTH,
      "locator": "https://www.homedepot.com/l/search",
      "hours": "most stores ~6a–10p"}),
    (("lowe's", "lowes"),
     {"name": "Lowe's", "fill": BOTH,
      "locator": "https://www.lowes.com/store",
      "hours": "most stores ~6a–10p"}),
    (("dollar general", "dollargeneral", " dg "),
     {"name": "Dollar General", "fill": INSTORE,
      "locator": "https://www.dollargeneral.com/store-directory",
      "hours": "most stores ~8a–10p"}),
    (("dollar tree", "family dollar"),
     {"name": "Dollar Tree", "fill": INSTORE,
      "locator": "https://www.dollartree.com/locations",
      "hours": "most stores ~8a–9p"}),
    (("newegg",),
     {"name": "Newegg", "fill": DELIVERY, "locator": "",
      "hours": "24/7 online · ships"}),
    (("ebay",),
     {"name": "eBay", "fill": DELIVERY, "locator": "",
      "hours": "24/7 online · ships from seller"}),
    (("pokemon center", "pokemoncenter"),
     {"name": "Pokémon Center", "fill": ONLINE, "locator": "",
      "hours": "24/7 online · official, ships"}),
    (("snkrs", "nike"),
     {"name": "Nike / SNKRS", "fill": ONLINE, "locator": "",
      "hours": "app/online drops · ships"}),
    (("kohl's", "kohls"),
     {"name": "Kohl's", "fill": BOTH,
      "locator": "https://www.kohls.com/stores.jsp",
      "hours": "most stores ~9a–9p"}),
    (("sephora",),
     {"name": "Sephora", "fill": BOTH,
      "locator": "https://www.sephora.com/happening/stores",
      "hours": "mall hours ~10a–9p"}),
    (("ulta",),
     {"name": "Ulta", "fill": BOTH,
      "locator": "https://www.ulta.com/stores",
      "hours": "most stores ~10a–9p"}),
    (("gamestop",),
     {"name": "GameStop", "fill": BOTH,
      "locator": "https://www.gamestop.com/stores/",
      "hours": "most stores ~11a–7p"}),
]

# text signals that REFINE the retailer default
_SHIP_SIGNALS = ("free shipping", "free ship", " fs ", " fs,", "ships free",
                 "s&s", "subscribe & save", "subscribe and save", " fs+")
_LOCAL_SIGNALS = ("in-store", "in store", "b&m", "ymmv", "clearance", "penny",
                  "pickup only", "in-store only", "your store", "select stores",
                  "reset", "shelf")
_PICKUP_SIGNALS = ("pickup", "in-store pickup", "bopis", "store pickup",
                   "curbside")


def detect_retailer(text: str) -> dict | None:
    """Which retailer a find names (first match wins). None = unknown."""
    t = f" {(text or '').lower()} "
    for keys, info in RETAILERS:
        if any(k in t for k in keys):
            return info
    return None


def fulfillment_of(text: str) -> dict:
    """The full 'how do I get it' answer for one find:
    {retailer, fill, locator, hours, known}. Signals in the title refine
    the retailer's default (a 'free shipping' clearance still ships)."""
    t = (text or "").lower()
    info = detect_retailer(text)
    if info is None:
        # unknown retailer — infer from signals alone, honestly
        if any(s in t for s in _LOCAL_SIGNALS):
            fill = INSTORE
        elif any(s in t for s in _SHIP_SIGNALS):
            fill = DELIVERY
        else:
            fill = ""
        return {"retailer": "", "fill": fill, "locator": "",
                "hours": "", "known": False}
    fill = info["fill"]
    has_ship = any(s in t for s in _SHIP_SIGNALS)
    has_local = any(s in t for s in _LOCAL_SIGNALS)
    has_pickup = any(s in t for s in _PICKUP_SIGNALS)
    if fill == INSTORE and has_ship:
        fill = BOTH                       # DG item that also ships
    elif fill == BOTH and has_local and not (has_ship or has_pickup):
        fill = INSTORE                    # explicitly in-store-only note
    return {"retailer": info["name"], "fill": fill,
            "locator": info["locator"], "hours": info["hours"], "known": True}


def fulfillment_line(text: str) -> str:
    """One compact line for a find card: badge · retailer · hours ·
    locator. Empty when nothing is knowable (honest silence)."""
    f = fulfillment_of(text)
    if not f["fill"] and not f["retailer"]:
        return ""
    bits = []
    if f["fill"]:
        bits.append(f["fill"])
    if f["retailer"]:
        bits.append(f["retailer"])
    if f["hours"]:
        bits.append(f["hours"])
    line = " · ".join(bits)
    if f["locator"]:
        line += f" · [find your store]({f['locator']})"
    return line


__all__ = ["DELIVERY", "INSTORE", "BOTH", "ONLINE", "RETAILERS",
           "detect_retailer", "fulfillment_of", "fulfillment_line"]
