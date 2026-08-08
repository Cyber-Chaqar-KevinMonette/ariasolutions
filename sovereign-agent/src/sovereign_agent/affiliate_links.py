"""affiliate_links.py — tag real retailer links with an affiliate id.

Kevin, 2026-07-25: "let's plan the affiliate marketing system... mainly
the third party affiliate links maybe? Whatever can bring us the most
money fast." The scout/deal-tracker system already posts real, live
retailer links to dozens of Discord channels continuously — this module
is the ONLY thing standing between that existing distribution and real
affiliate revenue: it tags a link for whichever network it recognizes,
and leaves everything else untouched.

Amazon Associates only for now (Kevin's choice — simplest mechanism,
highest-coverage retailer). The registry is deliberately per-domain and
easy to extend to other networks later without touching any call site —
`scout.py:link_for()` calls `tag_url()` once; every posting path (embeds,
digests, flex messages) inherits whatever's registered here.

Honesty by construction: an unconfigured or unmatched link passes through
completely unchanged. A missing/misconfigured tag must never break or
garble a real deal link — the relay always stands, same principle as
scout_verify.py's grounded-truth checking.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

__all__ = ["tag_url"]

_AMAZON_HOST_FRAGMENT = "amazon."


def _amazon_tag(*, data_dir=None) -> str:
    try:
        from sovereign_agent.credentials import read_env
        path = None
        if data_dir is not None:
            path = data_dir / "shop.env" if hasattr(data_dir, "__truediv__") else None
        return (read_env(path).get("AMAZON_ASSOCIATE_TAG") or "").strip()
    except Exception:  # noqa: BLE001 — a vault read hiccup must never break a link
        return ""


def _tag_amazon(url: str, *, data_dir=None) -> str:
    tag = _amazon_tag(data_dir=data_dir)
    if not tag:
        return url  # not configured — pass through unchanged, never guess
    try:
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if k != "tag"]
        query.append(("tag", tag))
        return urlunsplit((parts.scheme, parts.netloc, parts.path,
                          urlencode(query), parts.fragment))
    except Exception:  # noqa: BLE001 — a malformed URL is not this module's job to fix
        return url


# domain fragment -> tagging function. Checked in order; first match wins.
_NETWORKS: list[tuple[str, "callable"]] = [
    (_AMAZON_HOST_FRAGMENT, _tag_amazon),
]


def tag_url(url: str, *, data_dir=None) -> str:
    """Tag a real retailer URL for whichever affiliate network recognizes
    its domain. Untouched if the domain isn't registered, the network's
    key isn't vaulted, or the URL is empty/malformed — a real, working,
    untagged link is always better than a broken one."""
    url = (url or "").strip()
    if not url:
        return url
    try:
        host = urlsplit(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return url
    for fragment, tagger in _NETWORKS:
        if fragment in host:
            return tagger(url, data_dir=data_dir)
    return url
