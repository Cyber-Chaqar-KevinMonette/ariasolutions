"""Operator cockpit — Textual TUI for sovereign-agent (v0.2.15.3)."""
from .animated_glyph import AnimatedEffect, AnimatedGlyph
from .app import CockpitApp, CosmicFitnessScreen, HelpScreen, WorkflowsScreen, run
from .glyph_metrics import (
    WidthTable,
    overwide_glyphs,
    probe_terminal_widths,
)
from .glyph_stage import GlyphStage

# RippleFrame requires Textual; guard so the package still imports without it
# (mirrors the rest of the cockpit's optional-Textual discipline).
try:  # pragma: no cover - exercised only when Textual is present
    from .ripple_border import RippleFrame
except Exception:  # noqa: BLE001
    RippleFrame = None  # type: ignore[assignment]

__all__ = [
    "CockpitApp",
    "CosmicFitnessScreen",
    "HelpScreen",
    "WorkflowsScreen",
    "run",
    "GlyphStage",
    "RippleFrame",
    "AnimatedGlyph",
    "AnimatedEffect",
    "WidthTable",
    "probe_terminal_widths",
    "overwide_glyphs",
]
