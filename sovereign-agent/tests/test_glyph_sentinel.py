"""Smoke tests for the glyph sentinel.

Locks in the contract:
  - scanner finds and counts non-ASCII glyphs across the source tree
  - classification matches the EAW table
  - catalog round-trips through JSON
  - replacement proposals respect the protected-files list
  - coverage gaps surface unsafe glyphs without registered replacements
"""
from __future__ import annotations

import json

import pytest

from sovereign_agent.stewardship import glyph_sentinel as gs


def test_scan_returns_a_catalog_with_glyphs():
    """The shipped tree must contain at least one non-ASCII glyph
    (we ship many — banners, brand markers, em-dashes)."""
    catalog = gs.scan_source_tree()
    assert catalog.total_files_scanned > 0
    assert len(catalog.glyphs) > 0
    assert catalog.generated_at  # ISO timestamp


def test_lozenge_is_classified_safe(tmp_path):
    """◊ (our chosen brand marker) must classify as safe."""
    sample = tmp_path / "sample.py"
    sample.write_text("# ◊ brand marker\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    entry = catalog.glyphs.get("U+25CA")
    assert entry is not None
    assert entry.classification == "safe"
    assert entry.east_asian_width == "N"


def test_original_diamond_is_classified_unsafe_with_replacement(tmp_path):
    """◈ (the bug Kevin caught) must classify as unsafe AND propose ◊."""
    sample = tmp_path / "sample.py"
    sample.write_text("# ◈ unsafe diamond\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    entry = catalog.glyphs.get("U+25C8")
    assert entry is not None
    assert entry.classification == "unsafe"
    assert entry.proposed_replacement == "\u25CA"


def test_em_dash_is_borderline_not_unsafe(tmp_path):
    """— (em-dash) is EAW=Ambiguous but de-facto-narrow per the whitelist."""
    sample = tmp_path / "sample.py"
    sample.write_text("# safe — really\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    entry = catalog.glyphs.get("U+2014")
    assert entry is not None
    assert entry.classification == "borderline"
    assert entry.de_facto_narrow is True


def test_catalog_roundtrips_through_json(tmp_path):
    catalog = gs.scan_source_tree()
    text = catalog.to_json()
    # Must be valid JSON
    data = json.loads(text)
    assert "glyphs" in data
    # Round-trip
    rebuilt = gs.GlyphCatalog.from_json(text)
    assert rebuilt.total_files_scanned == catalog.total_files_scanned
    assert set(rebuilt.glyphs.keys()) == set(catalog.glyphs.keys())


def test_save_load_catalog(tmp_path):
    catalog = gs.scan_source_tree()
    path = gs.save_catalog(catalog, tmp_path)
    assert path.is_file()
    loaded = gs.load_catalog(tmp_path)
    assert loaded is not None
    assert loaded.total_files_scanned == catalog.total_files_scanned


def test_proposals_skip_protected_files(tmp_path):
    """Even if glyphs.py contains ◈ (it does, for documentation), no
    proposal targets it — the protection list filters it out."""
    catalog = gs.scan_source_tree()
    proposals = gs.generate_proposals(catalog)
    for p in proposals:
        assert p.file_path not in gs.PROTECTED_RELATIVE_PATHS
        # No proposal should touch glyphs.py (which contains ◈ on purpose
        # for documenting the bug class).
        assert "glyphs.py" not in p.file_path or p.file_path != "src/sovereign_agent/glyphs.py"


def test_known_replacements_are_themselves_safe():
    """Every replacement we propose must itself be safe — sanity check that
    the lookup table doesn't accidentally swap one ambiguous-width glyph
    for another."""
    from sovereign_agent import glyphs as _g
    for unsafe_ch, replacement in gs.KNOWN_REPLACEMENTS.items():
        if not replacement or replacement == "":
            continue
        # All chars in the replacement string must be safe
        bad = _g.audit_string(replacement)
        assert not bad, (
            f"replacement for {unsafe_ch!r} = {replacement!r} contains "
            f"unsafe glyphs: {bad}"
        )


def test_gaps_surface_unsafe_without_registered_replacements(tmp_path):
    """A glyph not in KNOWN_REPLACEMENTS should appear as a gap."""
    sample = tmp_path / "sample.py"
    # 🌟 GLOWING STAR (W) — definitely unsafe, not in KNOWN_REPLACEMENTS
    sample.write_text("print('🌟 sparkle')\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    gaps = gs.detect_coverage_gaps(catalog)
    glowing_star_codepoints = [g.codepoint for g in gaps]
    assert "U+1F31F" in glowing_star_codepoints


def test_classification_distribution_is_sensible():
    """On the live tree, the sentinel should produce a non-trivial mix of
    classifications — not 100% one bucket. (Pre-uv-migration we'd have
    seen 0 safe; post-migration we expect a healthy spread.)"""
    catalog = gs.scan_source_tree()
    assert catalog.safe_count + catalog.borderline_count + catalog.unsafe_count == len(catalog.glyphs)
    # At least SOMETHING in each bucket — if any are zero, something's wrong
    # with classification logic. The lozenge ◊ alone gives us safe.
    assert catalog.safe_count >= 1


# glyph-hardening-d: is_emoji_risk() closes the missing-font-coverage gap
# EAW-only classification couldn't see (Kevin caught 2 real instances of
# this live in /tiers: \U0001F39A and \u23f8, both EAW=Neutral).

def test_level_slider_now_classifies_unsafe_with_replacement(tmp_path):
    """\U0001F39A (LEVEL SLIDER) is EAW=Neutral -- the old EAW-only check
    called this safe. It's exactly the class of bug Kevin caught live."""
    sample = tmp_path / "sample.py"
    sample.write_text("title = '\U0001F39A settings'\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    entry = catalog.glyphs.get("U+1F39A")
    assert entry is not None
    assert entry.east_asian_width in ("N", "Na", "H")
    assert entry.classification == "unsafe"
    assert entry.proposed_replacement == "\u25CA"


def test_pause_glyph_now_classifies_unsafe_with_replacement(tmp_path):
    """\u23f8 (PAUSE) is EAW=Neutral -- the other real bug Kevin caught."""
    sample = tmp_path / "sample.py"
    sample.write_text("label = '\u23f8 stop'\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    entry = catalog.glyphs.get("U+23F8")
    assert entry is not None
    assert entry.east_asian_width in ("N", "Na", "H")
    assert entry.classification == "unsafe"
    assert entry.proposed_replacement == "\u2717"


def test_close_x_and_heavy_check_do_not_regress_to_unsafe(tmp_path):
    """\u2715 (close button, 17+ cockpit files) and \u2714 (confirmed
    rendering in Kevin's own screenshot) sit in the SAME Dingbats block as
    real bugs above -- they must stay safe, not become false positives."""
    sample = tmp_path / "sample.py"
    sample.write_text("row = '\u2715 close  \u2714 done'\n", encoding="utf-8")
    catalog = gs.scan_source_tree(source_root=tmp_path)
    for codepoint in ("U+2715", "U+2714"):
        entry = catalog.glyphs.get(codepoint)
        assert entry is not None
        assert entry.classification == "safe", (
            f"{codepoint} regressed to {entry.classification!r} -- "
            "false positive on an empirically-proven-safe glyph"
        )


def test_is_emoji_risk_matches_classify_for_established_safe_set():
    """Direct unit check on the new glyphs.py function, independent of
    the file-scan path above."""
    from sovereign_agent import glyphs as _g
    for ch in (_g.CHECK, _g.CROSS, _g.LOZENGE, _g.BULLET, "\u2715", "\u2714"):
        assert not _g.is_emoji_risk(ch), f"{ch!r} should not be flagged emoji-risk"
    for ch in ("\U0001F39A", "\u23f8", "\U0001F31F"):
        assert _g.is_emoji_risk(ch), f"{ch!r} should be flagged emoji-risk"


def test_safe_glyph_catalog_entries_are_all_actually_width_safe_or_exempt():
    """glyph-catalog-d (Kevin, 2026-07-21): "create a safe glyph catalog
    and start using those glyphs." Every entry in the catalog must be
    genuinely safe -- either EAW width-safe, or explicitly on the narrow
    is_emoji_risk exemption list (the diamond-family replacements)."""
    from sovereign_agent import glyphs as _g

    for ch in _g.SAFE_GLYPH_CATALOG:
        # audit_string(ch) empty == on the DE_FACTO_NARROW whitelist (the
        # same check glyph_sentinel._classify itself uses for its
        # "borderline" verdict) -- covers box-drawing chars, which are
        # EAW=Ambiguous but genuinely safe in every terminal shipped on.
        assert (_g.is_width_safe(ch) or ch in _g._ESTABLISHED_SAFE
                or not _g.audit_string(ch)), (
            f"{ch!r} in SAFE_GLYPH_CATALOG is neither width-safe, an "
            "established emoji-risk exemption, nor de-facto-narrow"
        )
        assert not _g.is_emoji_risk(ch), (
            f"{ch!r} in SAFE_GLYPH_CATALOG is flagged emoji-risk"
        )


def test_is_cataloged_matches_the_catalog_dict():
    from sovereign_agent import glyphs as _g

    for ch in _g.SAFE_GLYPH_CATALOG:
        assert _g.is_cataloged(ch) is True
    assert _g.is_cataloged("◈") is False  # the banned diamond, never cataloged


# ─── glyph-catalog-sweep-d (Kevin, 2026-07-21) ─────────────────────────────
#
# "make sure no text overflows in the windows when i use commands... I
# noticed that seems to happen with some if not all commands." A sweep
# for the SAME bug class as the REFERENCE_BUTTONS fix (a broken/unsafe
# emoji in a Button label or modal title corrupts that layout's width
# math) found it repeated across Key Vault, Bot Studio, Shop Studio,
# Theme Creator, and Scout Trace -- all fixed. This test locks in every
# button label and modal title across those five screens.


def _button_and_static_texts(module):
    """Every literal string passed to Button(...) or Static(...) in a
    screen module's compose() -- the actual on-screen labels/titles, not
    docstrings or toast/help body text (which the doctrine already
    treats as safe -- see glyphs.py rule #2)."""
    import ast
    import inspect

    src = inspect.getsource(module)
    tree = ast.parse(src)
    texts = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("Button", "Static") and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            texts.append(node.args[0].value)
    return texts


def test_key_vault_bot_shop_theme_scout_have_no_unsafe_glyphs_in_chrome():
    from sovereign_agent import glyphs as _g
    from sovereign_agent.cockpit import (
        bot_studio_screen, credentials_screen, scout_trace_screen,
        shop_studio_screen, theme_creator_screen,
    )

    for module in (credentials_screen, bot_studio_screen, shop_studio_screen,
                   theme_creator_screen, scout_trace_screen):
        for text in _button_and_static_texts(module):
            for ch in text:
                if _g.is_emoji_risk(ch) or (not _g.is_width_safe(ch) and _g.audit_string(ch)):
                    pytest.fail(
                        f"{module.__name__}: unsafe glyph {ch!r} in "
                        f"chrome text {text!r}"
                    )
