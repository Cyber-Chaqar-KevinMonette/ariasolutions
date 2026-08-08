"""warframe-flip-d (Kevin, 2026-07-27): "feel the texture of the market
today" — `sov scout warframe-report`, the daily digest command. No real
network: `_wf_get` and `WebhookDelivery` are both monkeypatched."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from sovereign_agent.cli import app
from sovereign_agent.config import Paths, SETTINGS


def _use_tmp_settings(tmp_path):
    object.__setattr__(SETTINGS, "paths",
                       Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data"))
    SETTINGS.paths.data_dir.mkdir(parents=True, exist_ok=True)


def _write_cache(data_dir, *, arcanes=None, riven_weapons=None):
    from sovereign_agent.discord_runtime.fetchers import _wf_save_cache
    _wf_save_cache(data_dir, {
        "fetched_at": 0, "sets": [], "relics": [],
        "arcanes": arcanes or [], "riven_weapons": riven_weapons or [],
        "id_to_slug": {}, "cursor": 0})


def test_no_cache_is_an_honest_no_op(tmp_path):
    _use_tmp_settings(tmp_path)
    r = CliRunner().invoke(app, ["scout", "warframe-report"])
    assert r.exit_code == 0
    assert "No cached market data" in r.output


def test_dry_run_ranks_arcanes_and_rivens(tmp_path, monkeypatch):
    _use_tmp_settings(tmp_path)
    _write_cache(SETTINGS.paths.data_dir,
                arcanes=[{"slug": "arcane_energize", "name": "Arcane Energize"},
                        {"slug": "arcane_ice", "name": "Arcane Ice"}],
                riven_weapons=[{"slug": "vectis", "name": "Vectis", "disposition": 1.15}])

    def fake_wf_get(opener, url, timeout=10.0):
        if "arcane_energize" in url:
            return {"data": [{"id": "1", "type": "sell", "platinum": 90, "visible": True,
                              "updatedAt": "2026-07-26T00:00:00Z", "rank": 0,
                              "user": {"ingameName": "A", "status": "online"}}]}
        if "arcane_ice" in url:
            return {"data": [{"id": "2", "type": "sell", "platinum": 5, "visible": True,
                              "updatedAt": "2026-07-26T00:00:00Z", "rank": 0,
                              "user": {"ingameName": "B", "status": "online"}}]}
        if "auctions/search" in url:
            return {"payload": {"auctions": [
                {"buyout_price": 300, "owner": {"status": "online"}},
                {"buyout_price": 250, "owner": {"status": "ingame"}}]}}
        return {"data": []}

    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_wf_get", fake_wf_get)

    # each of the two item-type channels (Kevin: "a whole warframe
    # category, with channels for item types") gets its OWN delivery
    sent: dict[str, list] = {}
    class _FakeDelivery:
        def __init__(self, env, live=False):
            self._env = env
        def send(self, text, embeds=None, username=""):
            sent[self._env] = embeds
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=False, dry_run=True, detail="dry-run")
    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", _FakeDelivery)

    r = CliRunner().invoke(app, ["scout", "warframe-report"])
    assert r.exit_code == 0, r.output
    assert "dry-run" in r.output
    assert set(sent) == {"DISCORD_TRACK_WARFRAME_ARCANES_RANK0_WEBHOOK_URL",
                         "DISCORD_TRACK_WARFRAME_RIVENS_WEBHOOK_URL"}

    arcane_embeds = sent["DISCORD_TRACK_WARFRAME_ARCANES_RANK0_WEBHOOK_URL"]
    arcane_embed = next(e for e in arcane_embeds if "Arcanes" in e["title"])
    assert arcane_embed["description"].index("Arcane Energize") < \
        arcane_embed["description"].index("Arcane Ice")

    riven_embeds = sent["DISCORD_TRACK_WARFRAME_RIVENS_WEBHOOK_URL"]
    riven_embed = next(e for e in riven_embeds if "Riven" in e["title"])
    assert "Vectis" in riven_embed["description"]
    assert "300" in riven_embed["description"]     # the highest buyout seen, not the lowest


def test_report_ignores_offline_arcane_sellers_and_riven_auctions(tmp_path, monkeypatch):
    # warframe-online-only-d (Kevin, 2026-07-27): "we want online users
    # only instead of offline users" — the daily digest must never quote
    # a price only an offline trader is actually offering.
    _use_tmp_settings(tmp_path)
    _write_cache(SETTINGS.paths.data_dir,
                arcanes=[{"slug": "arcane_energize", "name": "Arcane Energize"}],
                riven_weapons=[{"slug": "vectis", "name": "Vectis", "disposition": 1.15}])

    def fake_wf_get(opener, url, timeout=10.0):
        if "arcane_energize" in url:
            return {"data": [
                {"id": "1", "type": "sell", "platinum": 5, "visible": True,
                 "updatedAt": "2026-07-26T00:00:00Z", "rank": 0,
                 "user": {"ingameName": "Sleeping", "status": "offline"}},
                {"id": "2", "type": "sell", "platinum": 90, "visible": True,
                 "updatedAt": "2026-07-26T00:00:00Z", "rank": 0,
                 "user": {"ingameName": "Awake", "status": "online"}},
            ]}
        if "auctions/search" in url:
            return {"payload": {"auctions": [
                {"buyout_price": 999, "owner": {"status": "offline"}},
                {"buyout_price": 300, "owner": {"status": "online"}}]}}
        return {"data": []}

    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_wf_get", fake_wf_get)

    sent: dict[str, list] = {}
    class _FakeDelivery:
        def __init__(self, env, live=False):
            self._env = env
        def send(self, text, embeds=None, username=""):
            sent[self._env] = embeds
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=False, dry_run=True, detail="dry-run")
    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", _FakeDelivery)

    r = CliRunner().invoke(app, ["scout", "warframe-report"])
    assert r.exit_code == 0, r.output

    arcane_embeds = sent["DISCORD_TRACK_WARFRAME_ARCANES_RANK0_WEBHOOK_URL"]
    arcane_embed = next(e for e in arcane_embeds if "Arcanes" in e["title"])
    assert "90" in arcane_embed["description"]
    assert "5p" not in arcane_embed["description"]

    riven_embeds = sent["DISCORD_TRACK_WARFRAME_RIVENS_WEBHOOK_URL"]
    riven_embed = next(e for e in riven_embeds if "Riven" in e["title"])
    assert "300" in riven_embed["description"]
    assert "999" not in riven_embed["description"]


def test_a_failing_item_never_sinks_the_whole_report(tmp_path, monkeypatch):
    _use_tmp_settings(tmp_path)
    _write_cache(SETTINGS.paths.data_dir,
                arcanes=[{"slug": "broken", "name": "Broken"},
                        {"slug": "ok", "name": "OK Arcane"}])

    def fake_wf_get(opener, url, timeout=10.0):
        if "broken" in url:
            raise RuntimeError("network hiccup")
        return {"data": [{"id": "1", "type": "sell", "platinum": 20, "visible": True,
                          "updatedAt": "2026-07-26T00:00:00Z", "rank": 0,
                          "user": {"ingameName": "C", "status": "online"}}]}

    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_wf_get", fake_wf_get)

    class _FakeDelivery:
        def __init__(self, env, live=False): pass
        def send(self, text, embeds=None, username=""):
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=False, dry_run=True, detail="dry-run")
    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", _FakeDelivery)

    r = CliRunner().invoke(app, ["scout", "warframe-report"])
    assert r.exit_code == 0, r.output
