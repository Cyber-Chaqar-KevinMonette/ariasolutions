"""R3 tests — external pattern matching: Source include/exclude filters."""
from __future__ import annotations

from sovereign_agent.bot_projects import BotProject
from sovereign_agent.discord_runtime import BotRuntime, RateContract, Source
from sovereign_agent.discord_runtime.sources import Item, add_source, list_sources


# ── the filter matrix ────────────────────────────────────────────────────────
def test_no_filters_passes_everything():
    s = Source(name="s")
    assert s.item_passes("anything at all")


def test_include_requires_a_match():
    s = Source(name="s", include_patterns=["ps5", "playstation 5"])
    assert s.item_passes("PS5 console restocked!")        # case-insensitive
    assert s.item_passes("PlayStation 5 bundle in stock")
    assert not s.item_passes("Xbox Series X restocked")   # no include hit


def test_exclude_wins_over_include():
    s = Source(name="s", include_patterns=["ps5"], exclude_patterns=["controller"])
    assert s.item_passes("PS5 console drop")
    assert not s.item_passes("PS5 controller restock")    # excluded despite include


def test_regex_patterns_with_re_prefix():
    s = Source(name="s", include_patterns=[r"re:ps\s*5"])
    assert s.item_passes("PS 5 available") and s.item_passes("ps5 in stock")
    assert not s.item_passes("psp in stock")


def test_bad_regex_degrades_to_literal_never_breaks():
    s = Source(name="s", include_patterns=["re:[unclosed"])
    assert s.item_passes("found [unclosed bracket in title")
    assert not s.item_passes("normal title")              # literal miss, no crash


def test_filters_survive_store_round_trip(tmp_path):
    add_source(tmp_path, "P", Source(name="feed", include_patterns=["ps5"],
                                     exclude_patterns=["digital edition"]))
    got = list_sources(tmp_path, "P")[0]
    assert got.include_patterns == ["ps5"]
    assert got.exclude_patterns == ["digital edition"]


def test_old_sources_without_filter_fields_still_load(tmp_path):
    # a sources.json written before R3 has no filter keys
    import json
    from sovereign_agent.discord_runtime.sources import sources_path
    p = sources_path(tmp_path, "Old")
    p.write_text(json.dumps([{"name": "legacy", "url": "http://x",
                              "kind": "http", "allowed_min_interval_s": 60.0,
                              "enabled": True}]), encoding="utf-8")
    got = list_sources(tmp_path, "Old")[0]
    assert got.include_patterns == [] and got.item_passes("anything")


# ── runtime integration: filter → audit ─────────────────────────────────────
class _StubFetcher:
    def __init__(self, items): self._items = items
    def fetch(self, source): return list(self._items)


def test_runtime_filters_before_dedup_and_counts(tmp_path):
    src = Source(name="feed", allowed_min_interval_s=60,
                 include_patterns=["ps5"], exclude_patterns=["controller"])
    items = [Item("1", "PS5 console restock"),      # passes
             Item("2", "PS5 controller restock"),   # excluded
             Item("3", "Xbox restock")]             # no include hit
    rt = BotRuntime(BotProject(project_name="P", kind="restock-alert"), [src],
                    fetcher=_StubFetcher(items), data_dir=tmp_path)
    rep = rt.poll_once(now=1000.0)
    assert len(rep.new_alerts) == 1 and rep.new_alerts[0].item_id == "1"
    assert rep.filtered == 2
    assert "2 filtered" in rep.summary()
    # filtered items never entered seen-space → relaxing the filters later
    # lets them alert (they weren't burned by dedup)
    src.include_patterns = []
    src.exclude_patterns = []
    rep2 = rt.poll_once(now=1100.0)
    assert {a.item_id for a in rep2.new_alerts} == {"2", "3"}
