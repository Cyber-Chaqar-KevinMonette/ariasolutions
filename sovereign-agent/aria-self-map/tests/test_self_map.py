"""Real behavior tests for aria-self-map — prove she can produce an honest
'here is all of me' report, and that orphan detection is precise (real
integrity problems only, never a false alarm for the wholeness guardian).
"""
from __future__ import annotations

from sovereign_agent.self_map import (
    SelfMap,
    build_self_map,
    find_orphans,
    render_self_report,
    self_map_summary,
)


def _map():
    return SelfMap(
        sentinels=["timeout", "watchdog", "defense"],
        tools=[
            {"name": "aria_status", "tier": 0, "requires_approval": False},
            {"name": "read_session", "tier": 1, "requires_approval": False},
            {"name": "write_thing", "tier": 3, "requires_approval": True},
        ],
        channels=[{"name": "people", "tier": 3}, {"name": "financial", "tier": 2}],
        orphans=[],
        captured_at="2026-07-11T12:00:00Z",
    )


# ── find_orphans (the integrity core the guardian reads) ─────────────────
def test_no_orphans_when_all_declared_resolve():
    assert find_orphans({"a", "b", "c"}, {"a", "b", "c"}) == []


def test_declared_but_unresolvable_is_an_orphan():
    assert find_orphans({"a", "b", "c"}, {"a", "c"}) == ["b"]


def test_extra_resolvable_is_not_an_orphan():
    # something that resolves but wasn't in 'declared' is not an orphan.
    assert find_orphans({"a"}, {"a", "b"}) == []


def test_orphans_are_sorted_and_deduped():
    assert find_orphans(["z", "a", "a"], []) == ["a", "z"]


# ── counts / summary ─────────────────────────────────────────────────────
def test_counts_are_accurate():
    c = _map().counts
    assert c == {"sentinels": 3, "tools": 3, "channels": 2, "orphans": 0}


def test_summary_matches_counts():
    m = _map()
    assert self_map_summary(m) == m.counts


# ── render_self_report ───────────────────────────────────────────────────
def test_report_states_the_headline_counts():
    r = render_self_report(_map())
    assert "3 sentinels" in r and "3 tools" in r and "2 memory channels" in r


def test_report_has_all_capability_sections():
    r = render_self_report(_map())
    assert "## Sentinels" in r
    assert "## Tools" in r
    assert "## Memory channels" in r


def test_report_groups_tools_by_tier():
    r = render_self_report(_map())
    assert "Tier 0" in r and "Tier 1" in r and "Tier 3" in r
    assert "aria_status" in r and "write_thing" in r


def test_clean_map_says_wired_whole():
    r = render_self_report(_map())
    assert "No orphans" in r and "wired whole" in r


def test_orphans_are_loudly_surfaced():
    m = _map(); m.orphans = ["ghost_sentinel"]
    r = render_self_report(m)
    assert "orphan" in r.lower() and "ghost_sentinel" in r


def test_empty_map_renders_without_crashing():
    r = render_self_report(SelfMap())
    assert "0 sentinels" in r and "none registered" in r


# ── build_self_map (live gather, best-effort) ────────────────────────────
def test_build_self_map_reads_the_live_registries(tmp_path):
    # Runs against the real registered systems; must not raise and must find
    # real sentinels/tools (the running system has many of each).
    m = build_self_map(data_dir=tmp_path)
    assert isinstance(m, SelfMap)
    assert m.counts["sentinels"] > 0   # the real system has sentinels
    assert m.counts["tools"] > 0       # and tools
    # and it produces a coherent report over the live data
    assert "self-report" in render_self_report(m)
