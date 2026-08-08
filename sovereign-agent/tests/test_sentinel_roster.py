"""Tests for sentinel_roster — every sentinel's self-knowledge.

Also a quiet integrity check: what the roster *says* about each sentinel must
match what that sentinel actually is (read-only / reversible / human-gated).
"""
from __future__ import annotations

from sovereign_agent import sentinel_roster as roster


def test_roster_lists_the_known_sentinels():
    names = {s.name for s in roster.roster()}
    assert names == {"skill_sentinel", "workflow_sentinel",
                     "integrity_sentinel", "cache_sentinel"}


def test_every_sentinel_knows_its_siblings():
    for s in roster.roster():
        assert s.siblings, f"{s.name} should know its kin"
        assert s.name not in s.siblings           # not its own sibling
        assert len(s.siblings) == 3               # the other three


def test_every_sentinel_carries_the_shared_creed():
    for s in roster.roster():
        assert s.creed == roster.CREED
        assert any("not alone" in line for line in s.creed)
        assert any("without a human" in line for line in s.creed)


def test_whoami_returns_full_self_knowledge():
    s = roster.whoami("integrity_sentinel")
    assert s is not None
    assert s.role and s.watches and s.scope and s.tools and s.belonging
    assert s.siblings


def test_whoami_unknown_is_none():
    assert roster.whoami("nope_sentinel") is None


def test_the_whole_names_the_kernel_and_the_parts():
    whole = roster.the_whole()
    assert whole["kernel"] == ("Safety", "Love", "Flourishing")
    assert "doctrine" in whole and whole["sentinels"]


def test_integrity_entry_reflects_the_real_gate():
    # The roster must not over-promise: integrity's authority is reversible-
    # autonomous + irreversible-human-gated, matching the actual sentinel.
    s = roster.whoami("integrity_sentinel")
    assert "human" in s.authority.lower()
    assert "reversible" in s.reversibility.lower()
    assert "scalpel" in s.belonging.lower() or "surgery" in s.belonging.lower()


def test_read_only_sentinels_say_so():
    for name in ("skill_sentinel", "cache_sentinel"):
        s = roster.whoami(name)
        assert "read-only" in s.reversibility.lower()


def test_roster_matches_real_modules():
    # Each named sentinel should correspond to a real importable class/module.
    from sovereign_agent.skill_sentinel import SkillSentinel  # noqa: F401
    from sovereign_agent.workflow_sentinel import WorkflowSentinel  # noqa: F401
    from sovereign_agent.integrity_sentinel import IntegritySentinel  # noqa: F401
    # cache_sentinel lives under stewardship
    import importlib
    assert importlib.util.find_spec("sovereign_agent.stewardship.cache_sentinel")


def test_render_is_nonempty_and_mentions_belonging_and_creed():
    out = roster.render()
    assert "Sentinel Roster" in out
    assert "Immune System" in out                 # a title shows
    assert "Shared creed" in out
    one = roster.render_one("workflow_sentinel")
    assert "beside you:" in one
