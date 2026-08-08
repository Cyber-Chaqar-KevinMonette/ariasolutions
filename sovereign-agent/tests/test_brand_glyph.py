"""The unsafe diamond family can never return (Kevin, 2026-07-18 ×2).

glyphs.py's doctrine named ◈ (U+25C8) the canonical offender; Kevin's
second screenshot round proved the WHOLE EAW-Ambiguous diamond family
breaks terminals: ◇ U+25C7, ◆ U+25C6, ◈ U+25C8 (glyph_sentinel._classify
rules all three 'unsafe'). Safe replacements, sentinel-approved:
◊ U+25CA (brand), ❖ U+2756 (filled), ✦/✧/⟡.

This test now scans EVERY live module — not just cockpit surfaces — so
no future feature can ship an ambiguous diamond anywhere.
"""
from __future__ import annotations

from pathlib import Path

import sovereign_agent

UNSAFE = ("◈", "◇", "◆")   # the EAW-Ambiguous diamond family
# glyphs.py + glyph_sentinel.py DOCUMENT the offenders — they're exempt.
_EXEMPT = {"glyphs.py", "glyph_sentinel.py"}


def test_no_unsafe_diamond_anywhere_in_live_src(all_src_python_files):
    root = Path(sovereign_agent.__file__).parent
    offenders = []
    for p in all_src_python_files:
        if p.name in _EXEMPT:
            continue
        text = p.read_text(encoding="utf-8")
        for g in UNSAFE:
            if g in text:
                offenders.append(f"{p.relative_to(root)} ({g} U+{ord(g):04X})")
    assert not offenders, (
        f"EAW-Ambiguous diamonds shipped again in: {offenders} — use "
        "glyphs.BRAND_MARKER (◊) or ❖/✦/✧/⟡; see glyphs.py doctrine.")


def test_brand_marker_is_the_safe_lozenge():
    from sovereign_agent.glyphs import BRAND_MARKER
    assert BRAND_MARKER == "◊"          # ◊ — one cell, everywhere


def test_sentinel_agrees_the_family_is_unsafe():
    """The classifier itself is the authority — keep the test honest."""
    import unicodedata

    from sovereign_agent.stewardship.glyph_sentinel import _classify

    for g in UNSAFE:
        verdict, _ = _classify(g, unicodedata.east_asian_width(g))
        assert verdict == "unsafe", f"{g}: sentinel verdict changed to {verdict}"
    for g in ("◊", "❖", "✦", "✧", "⟡"):
        verdict, _ = _classify(g, unicodedata.east_asian_width(g))
        assert verdict == "safe", f"{g}: replacement no longer safe ({verdict})"
