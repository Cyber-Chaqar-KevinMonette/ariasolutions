"""dollargeneral-parser-d (Kevin, 2026-07-27): "add a dollar general
category for pokemon" — a REAL per-product parser for DollarGeneral.com,
built against a real captured search page (2026-07-27, query "pokemon").
The real search endpoint is `/product-search?q=<term>` — a bare
`/search?q=` 404s (found via the homepage's own search form action).
"""
from __future__ import annotations

from sovereign_agent.discord_runtime.fetchers import (
    _parse_dollargeneral,
    _SCRAPE_PARSERS,
)


def _card(upc: str, slug: str, title: str, price: str = "") -> str:
    price_html = (f'<span class="product-price product-card__current-price">'
                 f'${price}</span>' if price else "")
    return (
        'product-tile-wrapper"><div class="product-tile--variation-1">'
        '<div class="product-card">'
        f'<a class="product-card__navigation" href="/p/{slug}/{upc}">'
        f'<div class="product-card__image-container"></div></a>'
        f'<div class="product-card__details">{price_html}'
        f'<a href="/p/{slug}/{upc}" class="product--title">{title}</a>'
        '</div></div>'
    )


def _page(*cards: str) -> str:
    return "<html><body><div>" + "".join(cards) + "</div></body></html>"


def test_dollargeneral_registered_by_default():
    assert "www.dollargeneral.com" in _SCRAPE_PARSERS
    assert _SCRAPE_PARSERS["www.dollargeneral.com"] is _parse_dollargeneral


def test_parse_dollargeneral_extracts_real_fields():
    html = _page(
        _card("728192558375", "pokemon-trading-card-game-15-card-pack-1-ct",
              "Pok&eacute;mon Trading Card Game, 15 Card Pack, 1 ct", "8.00"),
        _card("034000243822", "hersheys-milk-chocolate-pokemon",
              "HERSHEY'S Milk Chocolate Pokemon, Candy Bar, 1.55 oz", "1.75"),
    )
    items = _parse_dollargeneral(
        html, "https://www.dollargeneral.com/product-search?q=pokemon")
    assert len(items) == 2
    assert items[0].id == "728192558375"
    assert items[0].text == "Pokémon Trading Card Game, 15 Card Pack, 1 ct — $8.00"
    assert items[0].url == ("https://www.dollargeneral.com/p/"
                            "pokemon-trading-card-game-15-card-pack-1-ct/728192558375")
    assert items[1].text == "HERSHEY'S Milk Chocolate Pokemon, Candy Bar, 1.55 oz — $1.75"


def test_parse_dollargeneral_missing_price_says_so_honestly():
    html = _page(_card("111", "some-item", "Some Item"))
    items = _parse_dollargeneral(html, "https://www.dollargeneral.com/product-search?q=x")
    assert items[0].text == "Some Item — price unknown"


def test_parse_dollargeneral_falls_back_when_no_tiles_match_at_all():
    """A site redesign shouldn't silently stop posting — it just gets
    less specific (the default whole-page-change alert), never crashes."""
    html = "<html><body>totally different page, no product tiles here</body></html>"
    items = _parse_dollargeneral(html, "https://www.dollargeneral.com/product-search?q=x")
    assert len(items) == 1
    assert "changed" in items[0].text


def test_parse_dollargeneral_never_raises_on_garbage():
    items = _parse_dollargeneral(
        'product-tile-wrapper"><a class="product-card__navigation" href="/p/x/',
        "https://www.dollargeneral.com/x")
    assert isinstance(items, list)   # falls back, doesn't raise


def test_end_to_end_through_scrape_fetcher(tmp_path):
    """The real integration point: a Source with kind=scrape against
    www.dollargeneral.com should get REAL parsed items, not the generic
    whole-page-hash fallback."""
    from sovereign_agent.discord_runtime.fetchers import ScrapeFetcher
    from sovereign_agent.discord_runtime.sources import Source

    html = _page(_card("222", "integration-item", "Integration Item", "5.00"))

    class _FakeSession:
        def visit(self, url, **kw):
            return html, 200

    src = Source(name="dg-pokemon-search",
                url="https://www.dollargeneral.com/product-search?q=pokemon",
                kind="scrape")
    items = ScrapeFetcher(session=_FakeSession()).fetch(src)
    assert len(items) == 1
    assert items[0].text == "Integration Item — $5.00"
