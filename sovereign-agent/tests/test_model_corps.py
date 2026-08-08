"""Tests for aria-model-corps: prove the persona is actually built from the real
doctrine files, not hand-copied prose that can silently drift from them."""
from __future__ import annotations

import pytest


def test_frozen_priorities_quoted_verbatim():
    """The preamble must contain mos_canon's actual Safety/Love/Flourishing
    statements, word for word — not a paraphrase that could drift from the
    sealed source."""
    from sovereign_agent.mos_canon import read_only_priorities
    from sovereign_agent.model_corps import build_god_tier_preamble

    preamble = build_god_tier_preamble()
    for p in read_only_priorities():
        assert p.name in preamble
        assert p.statement in preamble


def test_nine_dimensions_parsed_from_the_real_file():
    """GOD_TIER_STANDARD.md's nine numbered dimensions must all be found —
    this is the actual ratchet: if the doc gains/loses a dimension, this
    count changes with it, not silently drift out of sync."""
    from sovereign_agent.model_corps import parse_god_tier_dimensions

    dims = parse_god_tier_dimensions()
    assert len(dims) == 9
    names = [n for n, _ in dims]
    assert any("Honesty" in n for n in names)
    assert any("Safety" in n for n in names)
    assert any("Love" in n or "Flourishing" in n for n in names)
    # every floor line actually has content, not an empty capture
    assert all(floor.strip() for _, floor in dims)


def test_missing_standard_file_degrades_honestly():
    """A missing/renamed GOD_TIER_STANDARD.md must not crash persona
    generation — it degrades to the frozen priorities alone."""
    from pathlib import Path

    from sovereign_agent.model_corps import build_god_tier_preamble, parse_god_tier_dimensions

    missing = Path("/nonexistent/GOD_TIER_STANDARD.md")
    assert parse_god_tier_dimensions(missing) == []
    preamble = build_god_tier_preamble(missing)
    assert "Safety" in preamble  # frozen priorities still present
    assert "floor, not your ceiling" not in preamble  # dimension section correctly omitted


def test_build_role_persona_includes_role_paragraph_and_shared_preamble():
    from sovereign_agent.model_corps import ROLES, build_god_tier_preamble, build_role_persona

    preamble = build_god_tier_preamble()
    for role in ROLES:
        persona = build_role_persona(role)
        assert persona.startswith(preamble)
        assert len(persona) > len(preamble)  # the role paragraph actually got appended


def test_unknown_role_raises_loudly():
    from sovereign_agent.model_corps import build_role_persona

    with pytest.raises(ValueError, match="unknown model_corps role"):
        build_role_persona("not-a-real-role")


def test_two_roles_produce_different_personas():
    """A cheap sanity check against a copy-paste bug where every role gets
    the same text regardless of the role argument."""
    from sovereign_agent.model_corps import build_role_persona

    assert build_role_persona("coder") != build_role_persona("vision")
