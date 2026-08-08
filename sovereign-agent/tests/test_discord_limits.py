"""Tests for discord_limits — the caps named once, enforced once."""
from __future__ import annotations

from sovereign_agent.discord_limits import (
    EMBED_DESC_CHARS,
    EMBED_TOTAL_CHARS,
    EMBEDS_PER_MESSAGE,
    MSG_CONTENT_CHARS,
    chunk_embeds,
    clamp_embed,
    clamp_text,
    embed_chars,
    split_text,
)


def test_clamp_text_visible_never_silent():
    assert clamp_text("short", 100) == "short"
    out = clamp_text("x" * 300, 100)
    assert len(out) == 100 and out.endswith("…")


def test_clamp_embed_every_part():
    e = clamp_embed({"title": "t" * 999, "description": "d" * 9999,
                     "footer": {"text": "f" * 9999},
                     "fields": [{"name": "n" * 999, "value": "v" * 9999}] * 40})
    assert len(e["title"]) == 256 and len(e["description"]) == EMBED_DESC_CHARS
    assert len(e["footer"]["text"]) == 2048
    assert len(e["fields"]) == 25
    assert len(e["fields"][0]["value"]) == 1024


def test_chunk_embeds_honors_both_caps():
    small = [{"title": "p", "description": "x" * 100} for _ in range(23)]
    chunks = chunk_embeds(small)
    assert [len(c) for c in chunks] == [10, 10, 3]          # count cap
    big = [{"description": "y" * 3000} for _ in range(5)]
    chunks = chunk_embeds(big)
    assert all(sum(embed_chars(e) for e in c) <= EMBED_TOTAL_CHARS
               for c in chunks)
    assert sum(len(c) for c in chunks) == 5                 # nothing dropped
    assert chunk_embeds([]) == []


def test_split_text_smart_seams():
    assert split_text("") == []
    assert split_text("hello") == ["hello"]
    paras = "\n\n".join(f"paragraph {i} " + "w" * 400 for i in range(8))
    parts = split_text(paras, 1000)
    assert all(len(p) <= 1000 for p in parts)
    assert "".join(parts).replace("\n", "").replace(" ", "") == \
        paras.replace("\n", "").replace(" ", "")            # nothing lost
    # unbroken run → honest hard cut, still nothing lost
    blob = "z" * (MSG_CONTENT_CHARS * 2 + 5)
    parts = split_text(blob)
    assert sum(len(p) for p in parts) == len(blob)
    assert all(len(p) <= MSG_CONTENT_CHARS for p in parts)


def test_delivery_door_clamps_structurally():
    from sovereign_agent.discord_runtime.delivery import WebhookDelivery
    captured = {}

    def opener(url, data, timeout):
        import json
        captured.update(json.loads(data))
        class _R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _R()

    import os
    os.environ["TEST_LIMITS_WEBHOOK"] = "https://discord.com/api/webhooks/1/x"
    try:
        d = WebhookDelivery("TEST_LIMITS_WEBHOOK", live=True, opener=opener)
        d.send("c" * 5000, embeds=[{"title": "t" * 999}] * 15,
               username="u" * 200)
        assert len(captured["content"]) == MSG_CONTENT_CHARS
        assert len(captured["embeds"]) == EMBEDS_PER_MESSAGE
        assert len(captured["embeds"][0]["title"]) == 256
        assert len(captured["username"]) == 80
    finally:
        del os.environ["TEST_LIMITS_WEBHOOK"]
