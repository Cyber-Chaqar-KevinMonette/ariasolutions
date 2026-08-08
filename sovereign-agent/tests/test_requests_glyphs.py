"""Every inbox icon must pass her OWN glyph classifier — structurally.

Kevin's screenshot (2026-07-17) caught the note icon rendering as tofu;
the audit found ALL 19 icons in the requests maps predated the glyph
standard. This test pins the fix the same way the Discord Watch surfaces
are pinned: a future icon can't ship unclassified."""
from __future__ import annotations

import unicodedata


def test_every_inbox_icon_is_classifier_safe():
    from sovereign_agent.stewardship.glyph_sentinel import _classify
    from sovereign_agent.workflow.requests import (
        KIND_EMOJI, PRIORITY_EMOJI, STATUS_EMOJI)
    bad = []
    for family, m in (("kind", KIND_EMOJI), ("status", STATUS_EMOJI),
                      ("priority", PRIORITY_EMOJI)):
        for key, icon in m.items():
            for ch in icon:
                cls, _ = _classify(ch, unicodedata.east_asian_width(ch))
                if cls == "unsafe":
                    bad.append(f"{family}.{key}: {ch!r} U+{ord(ch):04X}")
    assert not bad, f"unsafe inbox glyphs: {bad}"
