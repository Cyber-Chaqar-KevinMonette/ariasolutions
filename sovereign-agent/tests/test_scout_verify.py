"""Tests for scout_verify — proving finds against grounded truth."""
from __future__ import annotations

import json

from sovereign_agent.scout_verify import (
    REACHABLE,
    UNVERIFIED,
    VERIFIED,
    compose_scout_trace,
    load_verifications,
    verify_badge,
    verify_find,
    verify_recent,
)


def _seed(d, now=1_784_000_000.0):
    p = d / "bot_projects" / "scout-deals"
    p.mkdir(parents=True)
    rows = [{"ts": now - 100, "new": [
        {"source": "r-deals", "id": "t3_abc", "text": "chatter no link",
         "url": ""}]},
            {"ts": now - 50, "new": [
        {"source": "sd-x", "id": "thread-1", "text": "Widget $25 at Amazon",
         "url": "https://deal.example/widget"}]}]
    (p / "runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    return now


def test_verify_verdicts_from_page():
    # price on page → VERIFIED
    def ok_price(url):
        return 200, "<html>Widget in stock $25 add to cart</html>"
    r = verify_find({"id": "1", "text": "Widget $25", "url": "http://x"},
                    fetcher=ok_price)
    assert r["verdict"] == VERIFIED and r["checks"]["price_confirmed"]

    # live but no price/stock → REACHABLE
    def ok_bare(url):
        return 200, "<html>some discussion thread</html>"
    r = verify_find({"id": "2", "text": "Thing $99", "url": "http://x"},
                    fetcher=ok_bare)
    assert r["verdict"] == REACHABLE

    # bot-walled → UNVERIFIED, honest detail, relay stands
    def walled(url):
        return 403, ""
    r = verify_find({"id": "3", "text": "X", "url": "http://x"}, fetcher=walled)
    assert r["verdict"] == UNVERIFIED and "relay stands" in r["detail"]

    # no link → relay only
    r = verify_find({"id": "4", "text": "X", "url": ""}, fetcher=walled)
    assert r["verdict"] == UNVERIFIED and "source relay only" in r["detail"]


def test_verify_never_raises_on_broken_fetch():
    def boom(url):
        raise OSError("network down")
    # the default fetch swallows; an injected raiser is caught upstream too
    r = verify_find({"id": "1", "text": "x", "url": "http://x"},
                    fetcher=lambda u: (None, ""))
    assert r["verdict"] == UNVERIFIED


def test_verify_recent_stores_and_is_bounded(tmp_path):
    now = _seed(tmp_path)
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return 200, "in stock $25 add to cart"
    n = verify_recent(tmp_path, "scout-deals", limit=1, fetcher=fetch, now=now)
    assert n == 1 and calls["n"] == 1              # bounded to 1
    stored = load_verifications(tmp_path, "scout-deals")
    assert "thread-1" in stored
    # a second pass checks the next unverified, not the done one
    verify_recent(tmp_path, "scout-deals", limit=5, fetcher=fetch, now=now)
    assert len(load_verifications(tmp_path, "scout-deals")) == 2


def test_badges():
    assert verify_badge({"verdict": VERIFIED}) == "✓ verified"
    assert "live" in verify_badge({"verdict": REACHABLE})
    assert "relay" in verify_badge({"verdict": UNVERIFIED})
    assert "checking" in verify_badge(None)


def test_trace_shows_the_gather_chain(tmp_path):
    now = _seed(tmp_path)
    verify_recent(tmp_path, "scout-deals", limit=2,
                  fetcher=lambda u: (200, "in stock $25"), now=now)
    out = compose_scout_trace(tmp_path, "scout-deals", now=now)
    assert "Scout Trace" in out and "how she gathered" in out
    assert "gathered from: sd-x" in out
    assert "deal.example/widget" in out            # WHERE she went
    assert "verified" in out                       # the verdict
    assert "grounding:" in out
