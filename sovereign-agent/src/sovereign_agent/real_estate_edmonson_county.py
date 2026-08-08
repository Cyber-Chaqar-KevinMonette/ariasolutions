"""real_estate_edmonson_county.py — Edmonson County, KY (Brownsville)
Master Commissioner foreclosure-sale listings.

Kevin (2026-08-01): "extend the real estate radar to a few good and active
real estate communities" -- diagnosed first that condos/apartments were
100% Reddit-sourced (dead, fleet-wide rate-limited, and Kevin is banned
from Reddit so the OAuth fix isn't available to him) while single-family
worked via county-record scrapers. Went looking for more counties near
the Hopkinsville/Clarksville/Nashville target area with the same kind of
scrapable public listing page.

Most small nearby KY counties (Trigg, Todd, Logan, Caldwell) have no
discoverable dedicated commissioner site. Two real, confirmed candidates
turned up on the official Kentucky Court of Justice master-commissioner
directory: Warren County (Bowling Green) and Edmonson County (Brownsville).
Warren County's scheduled-properties page renders its table via JavaScript
(confirmed by direct curl -- the raw HTML has zero listing rows, matching
what a plain requests-based fetch would see), so it needs the heavier
Playwright-based fetcher already built for Target/Best Buy, not this one --
left as a follow-up, not built here. Edmonson County's site (Weebly-built,
`wsite-*` classes) is genuinely server-rendered: curled directly and found
a real listing verbatim (case 22-CI-00063, Freedom Mortgage Corporation vs.
Thomas Benjamin Gulley et al., 25 Cornerstone Ct., Brownsville, KY,
$150,000.00), same lightweight-scrape pattern as Christian County.

Reuses CountyListing from real_estate_county_records.py -- Edmonson's rows
are the same shape (case, plaintiff/defendant, address, appraisal amount),
no need for a new dataclass.

One real wrinkle found live: the site posts a "SALE CANCELLED" banner
above the listing table on months with no sale, while still showing the
prior scheduled case row underneath it. Posting that row as a fresh find
would be misleading (it's exactly the cancelled sale), so a cancelled
sale block is parsed as zero listings, not stale-but-real ones.
"""
from __future__ import annotations

import re

from sovereign_agent.real_estate_county_records import CountyListing

__all__ = [
    "EDMONSON_COUNTY_KY_URL",
    "parse_edmonson_county_ky",
    "fetch_edmonson_county_items",
]

EDMONSON_COUNTY_KY_URL = "https://www.edmonsoncountymastercommissioner.com/sale-dates.html"

_CASE_ROW_RE = re.compile(
    r'<div class="paragraph">(?:(?!</div>).)*?\d{2}-CI-\d+.*?</div>',
    re.DOTALL,
)
_CANCELLED_RE = re.compile(r"SALE\s+CANCELLED", re.IGNORECASE)
_CASE_NO_RE = re.compile(r"(\d{2}-CI-\d+)")
_PARTIES_RE = re.compile(r"\d{2}-CI-\d+\s*(.+?)\s*(?:,?\s*et al\.?)?\s*(\d+\s[^,]+,\s*[A-Za-z .]+,\s*KY)", re.DOTALL)
_AMOUNT_RE = re.compile(r"(\$[\d,]+\.\d{2})")


def _strip_tags(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    return (text.replace("&nbsp;", " ").replace("&#8203;", "")
                .replace("&#038;", "&").replace("&amp;", "&"))


def parse_edmonson_county_ky(html: str) -> list[CountyListing]:
    """Edmonson County, KY Master Commissioner sale listings.
    https://www.edmonsoncountymastercommissioner.com/sale-dates.html
    Each listing is a `<div class="paragraph">` containing a "NN-CI-NNNNN"
    case number, "Plaintiff vs. Defendant" text, a street address ending
    in ", KY", and a dollar appraisal -- confirmed against the live page,
    not guessed."""
    out: list[CountyListing] = []
    for block in _CASE_ROW_RE.findall(html):
        text = _strip_tags(block)
        if _CANCELLED_RE.search(html[:html.find(block)]):
            continue  # this case row belongs to a cancelled sale block
        case_m = _CASE_NO_RE.search(text)
        case_no = case_m.group(1) if case_m else ""
        parties_m = _PARTIES_RE.search(text)
        parties = parties_m.group(1).strip().rstrip(",") if parties_m else ""
        address = parties_m.group(2).strip() if parties_m else ""
        amount_m = _AMOUNT_RE.search(text)
        amount = amount_m.group(1) if amount_m else ""
        if not (case_no and address):
            continue
        out.append(CountyListing(
            county="Edmonson County", state="KY",
            case_or_type=f"{case_no} {parties}".strip(),
            address=address, sale_date="", amount=amount,
            detail_url=EDMONSON_COUNTY_KY_URL, raw_text=text.strip(),
        ))
    return out


def _listing_id(listing: CountyListing) -> str:
    """Edmonson's page is one flat listings page (no per-listing detail
    URL), same situation as Montgomery County TN -- hash on the case
    number + address, the two fields that are genuinely unique per
    listing (matches real_estate_county_records._listing_id's fallback)."""
    import hashlib
    key = f"{listing.case_or_type}|{listing.address}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def fetch_edmonson_county_items(html: str, url: str) -> list:
    """`register_scrape_parser` contract: `(html, url) -> list[Item]`.
    Lazy-imports Item so this module has no hard dependency on
    discord_runtime at import time (matches real_estate_county_records.py's
    own lazy-import discipline)."""
    from sovereign_agent.discord_runtime.sources import Item
    return [
        Item(id=_listing_id(l), text=l.as_text(), url=l.detail_url or url)
        for l in parse_edmonson_county_ky(html)
    ]
