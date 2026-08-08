"""real_estate_county_records.py — county court-record scrapers for the two
target counties Kevin named (Christian County, KY and Montgomery County, TN,
Nashville/Clarksville/Hopkinsville area) after Reddit was ruled out (Kevin's
account is banned, so the OAuth fix built for the rest of the fleet isn't an
option for him). These are the real public-record signal sources: county
foreclosure/tax-sale court listings, confirmed by direct fetch (not guessed)
to be unauthenticated, structured, static HTML with no login/CAPTCHA — the
"easy" category from the sourcing research, versus tax-delinquent rolls
(seasonal-only, no persistent URL) and probate (docket-search only, no bulk
feed), both deprioritized to a manual check rather than automated.

Every listing is tagged with its county/state directly at scrape time
(known by construction — one parser per county) rather than extracted from
free text, per Kevin's ask: "have each post list the location and county
per post."
"""
from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = [
    "CountyListing",
    "parse_christian_county_ky",
    "parse_montgomery_county_tn",
    "fetch_christian_county_items",
    "fetch_montgomery_county_items",
    "CHRISTIAN_COUNTY_KY_URL",
    "MONTGOMERY_COUNTY_TN_URL",
]

CHRISTIAN_COUNTY_KY_URL = "https://christiancountymastercommissioner.com/listings/"
MONTGOMERY_COUNTY_TN_URL = "https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales"


@dataclass(frozen=True)
class CountyListing:
    county: str
    state: str
    case_or_type: str
    address: str
    sale_date: str
    amount: str
    detail_url: str
    raw_text: str

    def as_text(self) -> str:
        """A plain-text rendering for the existing real-estate pipeline
        (process_real_estate_item, actionability filters, strategy
        suggestion) — those all key off listing text, not structured
        fields, so this is the bridge into that pipeline."""
        parts = [
            f"{self.case_or_type}",
            f"Address: {self.address}, {self.county}, {self.state}",
        ]
        if self.sale_date:
            parts.append(f"Sale Date: {self.sale_date}")
        if self.amount:
            parts.append(f"Amount: {self.amount}")
        return " | ".join(parts)


def _strip_tags(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    text = (text.replace("&#8211;", "-").replace("&nbsp;", " ")
                .replace("&#038;", "&").replace("&amp;", "&"))
    return text


_ARTICLE_RE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.DOTALL)
_LINK_RE = re.compile(r'<a href="([^"]+)"[^>]*rel=bookmark>')


def parse_christian_county_ky(html: str) -> list[CountyListing]:
    """Christian County, KY Master Commissioner sale listings.
    https://christiancountymastercommissioner.com/listings/
    Each listing is a WordPress <article> with labeled fields
    ("Case Name:", "Case Number:", "Sale Date:", "Address:", "Judgment:")
    — confirmed against the live page, format varies slightly per post
    (some wrap fields in Elementor widgets, some don't) so this parses the
    stripped-text labels rather than depending on exact tag nesting."""
    out: list[CountyListing] = []
    for block in _ARTICLE_RE.findall(html):
        link_m = _LINK_RE.search(block)
        detail_url = link_m.group(1) if link_m else ""
        text = _strip_tags(block)

        _NEXT_LABEL = (r"(?:Case Name|Case Number|Sale Date|Address|Judgment"
                      r"|Appraisal|Attorney|Additional Information):")

        def field(label: str, _text: str = text) -> str:
            # Non-greedy, bounded by the next known label OR a real
            # newline — some listings put every field on one <p> with no
            # <br/> between "Case Name" and "Case Number" specifically,
            # which a plain `.+` would swallow whole.
            m = re.search(rf"{label}:\s*(.+?)(?=\n|{_NEXT_LABEL}|$)", _text)
            return m.group(1).strip() if m else ""

        case_name = field("Case Name")
        address_line = field("Address")
        # "1500 East 1st Street Hopkinsville, KY 42240 - (Get Map)" -> drop
        # the trailing "- (Get Map)" boilerplate. live-bug-d: the site mixes
        # the &#8211; ENTITY (converted to "-" above) with a literal en-dash
        # "–" character on some listings -- caught live (not in the fixture,
        # which happened to only contain entity-form listings), so match
        # both rather than just the hyphen.
        address = re.split(r"\s*[-–]\s*\(Get Map\)", address_line)[0].strip()
        sale_date = field("Sale Date")
        judgment = field("Judgment")
        if not case_name and not address:
            continue
        out.append(CountyListing(
            county="Christian County", state="KY",
            case_or_type=case_name or "Master Commissioner sale",
            address=address, sale_date=sale_date, amount=judgment,
            detail_url=detail_url, raw_text=text.strip(),
        ))
    return out


_TABLE_RE = re.compile(r'<figure class="table"><table>(.*?)</table></figure>', re.DOTALL)
_TYPE_RE = re.compile(r"<h2[^>]*><strong>([^<]+)</strong></h2>")
_ADDR_H3_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.DOTALL)
_BID_RE = re.compile(r"Opening Bid will start at\s*(\$[\d,]+(?:\.\d+)?)", re.IGNORECASE)
_SALE_DATE_RE = re.compile(
    r"(?:Bid Sale|FINAL AUCTION DATE)\s*:\s*"
    r"([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}"
    r"(?:,?\s*(?:@|at)\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|a\.m\.|p\.m\.)?)?)",
    re.IGNORECASE,
)


def parse_montgomery_county_tn(html: str) -> list[CountyListing]:
    """Montgomery County, TN Clerk & Master upcoming sales.
    https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales
    Each listing is a CKEditor `<figure class="table"><table>` block —
    confirmed against the live page (a colored header with the sale type
    and address, then detail rows: civil district, parcel ID, zoning,
    opening bid, sale date)."""
    out: list[CountyListing] = []
    for block in _TABLE_RE.findall(html):
        type_m = _TYPE_RE.search(block)
        sale_type = type_m.group(1).strip() if type_m else "Clerk & Master sale"
        addr_m = _ADDR_H3_RE.search(block)
        address = (_strip_tags(addr_m.group(1)).replace("\n", " ").strip()
                  if addr_m else "")
        text = _strip_tags(block)
        bid_m = _BID_RE.search(text)
        amount = bid_m.group(1) if bid_m else ""
        date_m = _SALE_DATE_RE.search(text)
        sale_date = date_m.group(1).strip() if date_m else ""
        if not address:
            continue
        out.append(CountyListing(
            county="Montgomery County", state="TN",
            case_or_type=sale_type, address=address, sale_date=sale_date,
            amount=amount, detail_url=MONTGOMERY_COUNTY_TN_URL,
            raw_text=text.strip(),
        ))
    return out


def _listing_id(listing: CountyListing) -> str:
    """Stable dedup key — the Master Commissioner detail page has a real
    per-listing URL; Montgomery's page doesn't (one flat listings page),
    so fall back to a hash of address+sale_date, which is stable across
    polls but changes if the listing itself is updated/relisted."""
    if listing.detail_url and listing.detail_url != MONTGOMERY_COUNTY_TN_URL:
        return listing.detail_url
    import hashlib
    key = f"{listing.address}|{listing.sale_date}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def fetch_christian_county_items(html: str, url: str) -> list:
    """`register_scrape_parser` contract: `(html, url) -> list[Item]`.
    Lazy-imports Item so this module has no hard dependency on
    discord_runtime at import time (matches the rest of this codebase's
    lazy-import discipline for optional/heavy subsystems)."""
    from sovereign_agent.discord_runtime.sources import Item
    return [
        Item(id=_listing_id(l), text=l.as_text(), url=l.detail_url or url)
        for l in parse_christian_county_ky(html)
    ]


def fetch_montgomery_county_items(html: str, url: str) -> list:
    from sovereign_agent.discord_runtime.sources import Item
    return [
        Item(id=_listing_id(l), text=l.as_text(), url=l.detail_url or url)
        for l in parse_montgomery_county_tn(html)
    ]
