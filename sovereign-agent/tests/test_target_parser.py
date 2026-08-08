"""target-parser-d (Kevin, 2026-07-27): a REAL per-product parser for
Target, built against a real captured search page (2026-07-27, zip
42240) — its search results are server-rendered directly into the HTML
with real `data-test` attributes, no JSON blob needed at all (unlike
Best Buy's Apollo SSR transport). Genuinely intermittent though — a
repeat live attempt in the same session got a synthetic timeout, a
later one succeeded — same best-effort honesty as Pokémon Center/Costco:
this parser only fires when the real markup is actually present, and
falls back to the honest whole-page-change alert otherwise.
"""
from __future__ import annotations

from sovereign_agent.discord_runtime.fetchers import (
    _parse_target,
    _SCRAPE_PARSERS,
)


def _card(tcin: str, slug: str, title: str, price: str = "", was: str = "") -> str:
    price_html = (f'<span class="h-text-bold h-text-lg" data-test="current-price">'
                 f'<span>${price}</span></span>' if price else "")
    was_html = (f'<div class="h-text-grayDark" data-test="comparison-price">was '
               f'<span>${was}</span></div>' if was else "")
    return (
        'data-test="@web/site-top-of-funnel/ProductCardWrapper" tabindex="-1">'
        f'<a href="/p/{slug}/-/A-{tcin}#lnk=sametab">'
        f'<picture data-test="@web/ProductCard/image"></picture></a>'
        f'<a data-test="@web/ProductCard/title" class="styles_ndsLink" '
        f'href="/p/{slug}/-/A-{tcin}#lnk=sametab">'
        f'<div class="styles_ndsTruncate" title="{title}">{title}</div></a>'
        f'{price_html}{was_html}'
    )


def _page(*cards: str) -> str:
    return "<html><body><div>" + "".join(cards) + "</div></body></html>"


def test_target_registered_by_default():
    assert "www.target.com" in _SCRAPE_PARSERS
    assert _SCRAPE_PARSERS["www.target.com"] is _parse_target


def test_parse_target_extracts_real_fields():
    html = _page(
        _card("94302124", "18-34-bigfoot-squishmallows-plush",
              '18&quot; Bigfoot Squishmallows Plush', "19.99", "24.99"),
        _card("94302120", "18-pink-cat-squishmallows-plush",
              '18&quot; Pink Cat Squishmallows Plush', "24.99"),
    )
    items = _parse_target(html, "https://www.target.com/s?searchTerm=squishmallow")
    assert len(items) == 2
    assert items[0].id == "94302124"
    assert items[0].text == '18" Bigfoot Squishmallows Plush — $19.99 (was $24.99)'
    assert items[0].url == "https://www.target.com/p/18-34-bigfoot-squishmallows-plush/-/A-94302124"
    # no discount when there's no "was" price — no "(was ...)" suffix
    assert items[1].text == '18" Pink Cat Squishmallows Plush — $24.99'


def test_parse_target_missing_price_says_so_honestly():
    html = _page(_card("111", "some-item", "Some Item"))
    items = _parse_target(html, "https://www.target.com/s?searchTerm=x")
    assert items[0].text == "Some Item — price unknown"


def test_parse_target_skips_cards_without_a_real_product_link():
    """Sponsored/bundle placements use a different card shape (no
    /p/<slug>/-/A-<tcin> link) — skipped, not an error."""
    html = ('<html><body>'
           'data-test="@web/site-top-of-funnel/ProductCardWrapper">'
           '<div>some sponsored placement, no real product link</div>'
           + _card("222", "real-item", "Real Item", "9.99")
           + '</body></html>')
    items = _parse_target(html, "https://www.target.com/s?searchTerm=x")
    assert len(items) == 1
    assert items[0].id == "222"


def test_parse_target_falls_back_when_no_cards_match_at_all():
    """A site redesign — or the captcha wall coming through instead of
    real content — shouldn't silently stop posting, just get less
    specific (the default whole-page-change alert), never crash."""
    html = "<html><body>totally different page, no product cards here</body></html>"
    items = _parse_target(html, "https://www.target.com/s?searchTerm=x")
    assert len(items) == 1
    assert "changed" in items[0].text


def test_parse_target_never_raises_on_garbage():
    items = _parse_target(
        'data-test="@web/site-top-of-funnel/ProductCardWrapper"'
        '<a href="/p/x/-/A-', "https://www.target.com/x")
    assert isinstance(items, list)   # falls back, doesn't raise


def test_end_to_end_through_scrape_fetcher(tmp_path):
    """The real integration point: a Source with kind=scrape against
    www.target.com should get REAL parsed items, not the generic
    whole-page-hash fallback."""
    from sovereign_agent.discord_runtime.fetchers import ScrapeFetcher
    from sovereign_agent.discord_runtime.sources import Source

    html = _page(_card("333", "integration-item", "Integration Item", "5.00"))

    class _FakeSession:
        def visit(self, url, **kw):
            return html, 200

    src = Source(name="target-squishmallows-search",
                url="https://www.target.com/s?searchTerm=squishmallow", kind="scrape")
    items = ScrapeFetcher(session=_FakeSession()).fetch(src)
    assert len(items) == 1
    assert items[0].text == "Integration Item — $5.00"
