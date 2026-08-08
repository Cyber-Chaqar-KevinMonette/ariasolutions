"""real_estate_lien_auctions.py — a seasonal (not continuous-poll) check
for Christian County, KY's delinquent property tax sale date/registration
deadline announcement.

Kevin (2026-08-01): "add liens... for title auctions or whatever" — a real,
distinct real-estate strategy (buying tax LIEN certificates at auction, not
the property itself). Researched earlier this session (2026-08-01): neither
county publishes a persistent, structured LIST of delinquent properties —
Kentucky legally requires certificates of delinquency to be posted only in
a ~30-day pre-sale window, and Montgomery County TN's Trustee page has no
structured content at all (confirmed twice, live). What IS real and stable:
Christian County's tax-sale-date announcement page, which states the sale
date and registration deadline in plain text once set for the year —
verified live 2026-08-01 ("The Christian County Clerk Delinquent Property
Tax Sale date is July 28, 2026...").

Kevin explicitly agreed this should be a periodic seasonal check, not a
continuous poller — see build_source_url's long default interval.
Montgomery County has no scraper here; nothing structured exists to scrape
(a manual check is the honest alternative to a scraper that would silently
find nothing all year).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = ["TaxSaleAnnouncement", "parse_christian_county_tax_sale_date",
           "CHRISTIAN_COUNTY_TAX_SALE_URL", "SEASONAL_CHECK_INTERVAL_S"]

CHRISTIAN_COUNTY_TAX_SALE_URL = "https://christiancountyky.gov/tax-sale-date"

# "Seasonal check" per Kevin's own choice, not a continuous poller — this
# content changes at most once a year. A week is frequent enough to catch
# the announcement promptly without hammering a small county site.
SEASONAL_CHECK_INTERVAL_S = 7 * 24 * 3600


@dataclass(frozen=True)
class TaxSaleAnnouncement:
    sale_date: str
    registration_deadline: str
    phone: str
    raw_text: str

    def as_text(self) -> str:
        parts = ["🔔 Christian County, KY Delinquent Property Tax Sale"]
        if self.sale_date:
            parts.append(f"Sale Date: {self.sale_date}")
        if self.registration_deadline:
            parts.append(f"Register by: {self.registration_deadline}")
        if self.phone:
            parts.append(f"Questions: {self.phone}")
        parts.append("(tax LIEN certificate sale — buying the lien, not the property)")
        return " | ".join(parts)


_SALE_DATE_RE = re.compile(
    r"Delinquent Property Tax Sale date is\s*([A-Za-z]+ \d{1,2},? \d{4})",
    re.IGNORECASE)
_DEADLINE_RE = re.compile(
    r"register with the County Clerk.{0,40}?by close of business on\s*"
    r"([A-Za-z]+ \d{1,2},? \d{4})", re.IGNORECASE | re.DOTALL)
_PHONE_RE = re.compile(r"call\s*\(?(\d{3})\)?[\s.-]*(\d{3})[\s.-]*(\d{4})", re.IGNORECASE)


def _strip_tags(html: str) -> str:
    # live-bug-d lesson from real_estate_county_records.py, applied
    # up front here instead of relearned: tags and entities interleave
    # unpredictably ("<b>&nbsp;</b><u><b>July 28, 2026</b></u>"), so every
    # regex below matches against fully-stripped plain text, never raw
    # HTML with tags still interspersed.
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&rsquo;", "'")
                .replace("&amp;", "&"))
    text = re.sub(r"[ \t]+", " ", text)
    return text


def parse_christian_county_tax_sale_date(html: str) -> TaxSaleAnnouncement | None:
    """Verified against the real live page (2026-08-01). Returns None if
    the expected sale-date sentence isn't found — e.g. the county hasn't
    posted this year's date yet, which is a real, honest, non-error state
    (not every check finds something new)."""
    text = _strip_tags(html)
    m = _SALE_DATE_RE.search(text)
    if not m:
        return None
    sale_date = m.group(1).strip().rstrip(",")
    dm = _DEADLINE_RE.search(text)
    deadline = dm.group(1).strip().rstrip(",") if dm else ""
    pm = _PHONE_RE.search(text)
    phone = f"({pm.group(1)}) {pm.group(2)}-{pm.group(3)}" if pm else ""
    return TaxSaleAnnouncement(
        sale_date=sale_date, registration_deadline=deadline, phone=phone,
        raw_text=text.strip(),
    )


def fetch_christian_county_tax_sale_items(html: str, url: str) -> list:
    """`register_scrape_parser` contract: `(html, url) -> list[Item]`. A
    dedup id built from the sale date itself — a NEW id (and a fresh
    alert) only when the date actually changes year to year, matching
    "seasonal check" rather than re-alerting the same date every poll."""
    from sovereign_agent.discord_runtime.sources import Item
    import hashlib

    ann = parse_christian_county_tax_sale_date(html)
    if ann is None:
        return []
    ident = hashlib.sha256(ann.sale_date.encode("utf-8")).hexdigest()[:16]
    return [Item(id=f"tax-sale-{ident}", text=ann.as_text(), url=url)]
