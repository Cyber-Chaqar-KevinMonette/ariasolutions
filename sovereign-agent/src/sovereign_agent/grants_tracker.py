"""grants_tracker.py — a real, live, no-auth-required tracker for federal
grant/funding opportunities via grants.gov's public search API.

Kevin (2026-08-01): "income securing category... grants + government
incentive programs." Verified live (curl'd directly, not just documented):
`POST https://api.grants.gov/v1/api/search2` needs no API key, returns real
paginated opportunities (hitCount 1717+ open at verification time) with
`dateRangeOptions` support for "posted in the last N days" — exactly what a
periodic poller needs to only surface genuinely new/updated opportunities.

Registered as a custom Fetcher (kind="grants-gov") rather than forced through
HttpJsonFetcher, which only supports GET — grants.gov's search needs a POST
with a JSON body. Search parameters are encoded in the Source's `url` as a
query string (keyword=..., fundingCategories=...) since Source has no body
field; the fetcher decodes them into the real POST payload.
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


__all__ = [
    "GrantOpportunity",
    "parse_search2_response",
    "GrantsGovFetcher",
    "SEARCH2_URL",
    "build_source_url",
]

SEARCH2_URL = "https://api.grants.gov/v1/api/search2"

# Days-since-posted buckets the API actually documents/accepts.
_VALID_DATE_RANGES = (3, 7, 14, 21, 28, 35, 42, 49, 56)


def build_source_url(*, keyword: str = "", opp_statuses: str = "forecasted|posted",
                     posted_within_days: int = 14) -> str:
    """A Source.url encoding search2's real parameters (id used at fetch
    time to reconstruct the POST body). posted_within_days is clamped to
    the buckets the API documents, not an arbitrary number."""
    days = min(_VALID_DATE_RANGES, key=lambda d: abs(d - posted_within_days))
    from urllib.parse import urlencode
    qs = urlencode({
        "keyword": keyword, "oppStatuses": opp_statuses,
        "postedDays": str(days),
    })
    return f"{SEARCH2_URL}?{qs}"


@dataclass(frozen=True)
class GrantOpportunity:
    opp_id: str
    number: str
    title: str
    agency: str
    open_date: str
    close_date: str
    status: str

    def as_text(self) -> str:
        parts = [f"{self.title}", f"Agency: {self.agency}", f"Opportunity #: {self.number}"]
        if self.open_date:
            parts.append(f"Posted: {self.open_date}")
        if self.close_date:
            parts.append(f"Closes: {self.close_date}")
        parts.append(f"Status: {self.status}")
        return " | ".join(parts)

    @property
    def url(self) -> str:
        return f"https://www.grants.gov/search-results-detail/{self.opp_id}"


def parse_search2_response(body: dict) -> list[GrantOpportunity]:
    """Parses the REAL response shape (verified live 2026-08-01):
    {"errorcode": 0, "data": {"hitCount": N, "oppHits": [{"id", "number",
    "title", "agencyCode", "agency", "openDate", "closeDate", "oppStatus",
    "docType", "cfdaList"}, ...]}}. Never raises on an unexpected shape —
    returns [] and lets the caller's own outcome-reporting handle it."""
    if not isinstance(body, dict):
        return []
    if body.get("errorcode") not in (0, None):
        return []
    hits = ((body.get("data") or {}).get("oppHits")) or []
    out: list[GrantOpportunity] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        opp_id = str(h.get("id") or "")
        if not opp_id:
            continue
        out.append(GrantOpportunity(
            opp_id=opp_id, number=str(h.get("number") or ""),
            title=str(h.get("title") or "(untitled opportunity)"),
            agency=str(h.get("agency") or h.get("agencyCode") or ""),
            open_date=str(h.get("openDate") or ""),
            close_date=str(h.get("closeDate") or ""),
            status=str(h.get("oppStatus") or ""),
        ))
    return out


class GrantsGovFetcher:
    """`register`-style custom Fetcher (matches the WarframeFlipFetcher/
    ScrapeFetcher pattern already in this codebase) — `fetch(source) ->
    list[Item]`. POSTs a JSON body to search2 rather than GETting, which is
    why this isn't just routed through HttpJsonFetcher."""

    def __init__(self, opener=None, timeout: float = 10.0, on_outcome=None) -> None:
        self._opener = opener
        self._timeout = timeout
        self._on_outcome = on_outcome

    def _report(self, source, ok: bool, detail: str) -> None:
        if self._on_outcome is None:
            return
        try:
            self._on_outcome(source.name, ok, detail)
        except Exception:  # noqa: BLE001
            pass

    def fetch(self, source) -> list:
        from sovereign_agent.discord_runtime.sources import Item

        parsed = urlparse(source.url or "")
        qs = parse_qs(parsed.query)
        payload = {
            "keyword": (qs.get("keyword") or [""])[0],
            "oppStatuses": (qs.get("oppStatuses") or ["forecasted|posted"])[0],
            "rows": 25,
            "dateRangeOptions": {"index": "1", "value": (qs.get("postedDays") or ["14"])[0]},
        }
        opener = self._opener
        if opener is None:  # pragma: no cover — tests inject
            import urllib.request

            def opener(url, data, headers, timeout):  # type: ignore[misc]
                req = urllib.request.Request(
                    url, data=data, headers=headers, method="POST")
                return urllib.request.urlopen(req, timeout=timeout)
        try:
            data = _json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            with opener(SEARCH2_URL, data, headers, self._timeout) as resp:  # type: ignore[misc]
                raw = resp.read()
            body = _json.loads(raw)
        except Exception as exc:  # noqa: BLE001 — a flaky API never crashes the fleet
            code = getattr(exc, "code", None)
            self._report(source, False, f"HTTP {code}" if code is not None else type(exc).__name__)
            return []
        opps = parse_search2_response(body)
        self._report(source, True, f"{len(opps)} opportunity(ies)")
        return [Item(id=o.opp_id, text=o.as_text(), url=o.url) for o in opps]
