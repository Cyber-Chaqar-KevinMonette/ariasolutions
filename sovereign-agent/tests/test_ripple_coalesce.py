"""Tests for the ripple-border coalescing patch (Segment.simplify).

The rippling frame emits one styled Segment per border cell. Without coalescing
that is one terminal quad per cell, and on a fractionally-scaled display the GPU
leaves a ~1px seam between adjacent quads — the faint grid on the borders.
Merging consecutive segments that share an identical Style collapses
same-coloured runs into single wide quads — fewer seams, fewer segments to diff
— with ZERO change to the rendered cells.

These tests pin the post-patch guarantees:
  • coalesced: no two ADJACENT segments in a strip share an identical style
    (this FAILS on the un-patched renderer, so it proves the patch is live)
  • geometry safe: total cell length per strip is unchanged
  • effective: a smooth single-colour frame merges to far fewer segments than
    it has cells
"""
from __future__ import annotations

import pytest

pytest.importorskip("textual")
pytest.importorskip("rich")

from rich.cells import cell_len  # noqa: E402
from textual.geometry import Region  # noqa: E402

from sovereign_agent.cockpit.ripple_border import (  # noqa: E402
    RIPPLE_IDLE,
    ripple_frame_strips,
)

BASE = (200, 60, 60)
BG = (20, 8, 10)


def _strips(w: int, h: int):
    return ripple_frame_strips(w, h, 0.0, BASE, BG, Region(0, 0, w, h), RIPPLE_IDLE)


def test_no_adjacent_identical_styles():
    """The simplify guarantee — and a direct check the patch is applied."""
    for strip in _strips(40, 8):
        segs = list(strip)
        for a, b in zip(segs, segs[1:]):
            assert a.style != b.style, (
                "adjacent segments share a style — Segment.simplify did not run"
            )


def test_width_invariant():
    """Coalescing must not change the rendered geometry."""
    w, h = 40, 8
    strips = _strips(w, h)
    assert len(strips) == h
    for strip in strips:
        assert sum(cell_len(seg.text) for seg in strip) == w


def test_runs_actually_merge_on_smooth_wave():
    """The smooth top edge should collapse to far fewer segments than cells."""
    w = 60
    top = list(_strips(w, 6)[0])
    assert len(top) < w, "smooth wave should coalesce into far fewer segments than cells"


@pytest.mark.parametrize("size", [(20, 4), (33, 7), (80, 24)])
def test_width_invariant_various_sizes(size):
    w, h = size
    for strip in _strips(w, h):
        assert sum(cell_len(seg.text) for seg in strip) == w
