"""retailer-scrape-d (Kevin, 2026-07-27): a REAL per-product parser for
Best Buy, built against a real captured search page (2026-07-27) — its
search results are embedded as Apollo GraphQL SSR-hydration payloads
(`ApolloSSRDataTransport`), not plain HTML or a single clean JSON blob.
Target was investigated the same evening and found to consistently
return a CAPTCHA challenge on its real product-data endpoint
(`redsky_aggregations/v1/web/plp_search_v2`), even after the homepage
warm-up that cleared Pokémon Center — so Target intentionally has no
per-product parser here; it still gets a real, honest "page changed"
alert via the default fallback, not a fabricated one.
"""
from __future__ import annotations

from sovereign_agent.discord_runtime.fetchers import (
    _extract_apollo_ssr_blobs,
    _parse_bestbuy,
    _SCRAPE_PARSERS,
)


def _push_html(*blobs: str) -> str:
    body = "".join(
        f'<script>(window[Symbol.for("ApolloSSRDataTransport")] ??= []).push({b});</script>'
        for b in blobs)
    return f"<html><head></head><body>{body}</body></html>"


def _search_blob(documents_json: str, key: str = ":R1:") -> str:
    return ('{"rehydrate":{"' + key + '":{"data":{"detailedProductSearch":'
           '{"__typename":"ProductSearch","documents":' + documents_json +
           '}},"networkStatus":7}}}')


def test_bestbuy_registered_by_default():
    assert "www.bestbuy.com" in _SCRAPE_PARSERS
    assert _SCRAPE_PARSERS["www.bestbuy.com"] is _parse_bestbuy


def test_extract_apollo_ssr_blobs_brace_matches_nested_json():
    # a value containing literal { and } inside a STRING must not confuse
    # the brace-matcher into stopping early — the classic naive-regex bug
    html = _push_html('{"rehydrate":{"k":{"data":{"note":"a {tricky} value"}}}}')
    blobs = _extract_apollo_ssr_blobs(html)
    assert len(blobs) == 1
    assert blobs[0]["rehydrate"]["k"]["data"]["note"] == "a {tricky} value"


def test_extract_apollo_ssr_blobs_sanitizes_undefined():
    html = _push_html('{"rehydrate":{"k":{"data":undefined,"networkStatus":7}}}')
    blobs = _extract_apollo_ssr_blobs(html)
    assert blobs[0]["rehydrate"]["k"]["data"] is None


def test_parse_bestbuy_extracts_real_fields():
    docs = ('[{"__typename":"SearchProduct","product":{"skuId":"1111111",'
           '"name":{"title":"Test GPU One"},'
           '"price":{"customerPrice":299.99,"displayableRegularPrice":349.99},'
           '"url":{"pdp":"https://www.bestbuy.com/product/test-one/1111111"}}},'
           '{"__typename":"SearchProduct","product":{"skuId":"2222222",'
           '"name":{"title":"Test GPU Two"},'
           '"price":{"customerPrice":499.99,"displayableRegularPrice":499.99},'
           '"url":{"pdp":"https://www.bestbuy.com/product/test-two/2222222"}}}]')
    html = _push_html(_search_blob(docs))
    items = _parse_bestbuy(html, "https://www.bestbuy.com/site/searchpage.jsp?st=gpu")

    assert len(items) == 2
    assert items[0].id == "1111111"
    assert items[0].text == "Test GPU One — $299.99 (was $349.99)"
    assert items[0].url == "https://www.bestbuy.com/product/test-one/1111111"
    # no discount when regular == current — no "(was ...)" suffix
    assert items[1].text == "Test GPU Two — $499.99"


def test_parse_bestbuy_falls_back_to_variation_display_title():
    docs = ('[{"__typename":"SearchProduct","product":{"skuId":"333",'
           '"productVariationListDisplay":{"title":"Fallback Name"},'
           '"price":{"customerPrice":10},'
           '"url":{"pdp":"https://www.bestbuy.com/product/x/333"}}}]')
    html = _push_html(_search_blob(docs))
    items = _parse_bestbuy(html, "https://www.bestbuy.com/site/searchpage.jsp?st=x")
    assert items[0].text == "Fallback Name — $10"


def test_parse_bestbuy_missing_name_says_so_honestly():
    docs = ('[{"__typename":"SearchProduct","product":{"skuId":"444",'
           '"price":{"customerPrice":10},'
           '"url":{"pdp":"https://www.bestbuy.com/product/x/444"}}}]')
    html = _push_html(_search_blob(docs))
    items = _parse_bestbuy(html, "https://www.bestbuy.com/site/searchpage.jsp?st=x")
    assert items[0].text.startswith("Unknown item")


def test_parse_bestbuy_skipping_every_skuless_document_falls_back_safely():
    """If every document in a batch is missing a SKU (a genuine anomaly),
    falling back to the whole-page-change alert is the safe choice —
    still says SOMETHING, rather than going silent for that tick."""
    docs = ('[{"__typename":"SearchProduct","product":{'
           '"name":{"title":"No SKU"},"price":{"customerPrice":10}}}]')
    html = _push_html(_search_blob(docs))
    items = _parse_bestbuy(html, "https://www.bestbuy.com/site/searchpage.jsp?st=x")
    assert len(items) == 1 and "changed" in items[0].text


def test_parse_bestbuy_skips_only_the_skuless_ones_when_others_are_fine():
    docs = ('[{"__typename":"SearchProduct","product":{'
           '"name":{"title":"No SKU"},"price":{"customerPrice":10}}},'
           '{"__typename":"SearchProduct","product":{"skuId":"999",'
           '"name":{"title":"Has SKU"},"price":{"customerPrice":20},'
           '"url":{"pdp":"https://www.bestbuy.com/product/z/999"}}}]')
    html = _push_html(_search_blob(docs))
    items = _parse_bestbuy(html, "https://www.bestbuy.com/site/searchpage.jsp?st=x")
    assert len(items) == 1
    assert items[0].id == "999"


def test_parse_bestbuy_falls_back_when_structure_is_absent():
    """A site redesign shouldn't silently stop posting — it just gets
    less specific (the default whole-page-change alert), never crashes."""
    html = "<html><body>totally different page, no apollo data here</body></html>"
    items = _parse_bestbuy(html, "https://www.bestbuy.com/site/searchpage.jsp?st=x")
    assert len(items) == 1
    assert "changed" in items[0].text


def test_parse_bestbuy_never_raises_on_garbage():
    items = _parse_bestbuy("<script>(window[Symbol.for(\"ApolloSSRDataTransport\")] "
                          "??= []).push({not valid json here);</script>",
                          "https://www.bestbuy.com/x")
    assert isinstance(items, list)   # falls back, doesn't raise


def test_end_to_end_through_scrape_fetcher(tmp_path):
    """The real integration point: a Source with kind=scrape against
    www.bestbuy.com should get REAL parsed items, not the generic
    whole-page-hash fallback."""
    from sovereign_agent.discord_runtime.fetchers import ScrapeFetcher
    from sovereign_agent.discord_runtime.sources import Source

    docs = ('[{"__typename":"SearchProduct","product":{"skuId":"555",'
           '"name":{"title":"Integration GPU"},'
           '"price":{"customerPrice":50},'
           '"url":{"pdp":"https://www.bestbuy.com/product/y/555"}}}]')
    html = _push_html(_search_blob(docs))

    class _FakeSession:
        def visit(self, url, **kw):
            return html, 200

    src = Source(name="bestbuy-gpu-search",
                url="https://www.bestbuy.com/site/searchpage.jsp?st=gpu", kind="scrape")
    items = ScrapeFetcher(session=_FakeSession()).fetch(src)
    assert len(items) == 1
    assert items[0].text == "Integration GPU — $50"
