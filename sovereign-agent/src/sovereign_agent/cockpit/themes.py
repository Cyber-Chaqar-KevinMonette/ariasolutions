"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/themes.py — Aria's curated theme spectrum                       ║
║                                                                           ║
║  Textual 8 ships 21 built-in themes (textual-dark/light, nord, gruvbox, ║
║  4× catppuccin, dracula, tokyo-night, monokai, flexoki, 2× solarized,   ║
║  3× rose-pine, 2× atom-one, 2× ansi). Many of those feel like           ║
║  near-duplicates from the operator's seat — the catppuccin family alone ║
║  has 4 variants that are mostly the same theme with different           ║
║  saturation curves.                                                      ║
║                                                                           ║
║  This module REGISTERS 16 additional themes designed to feel             ║
║  distinct — each one named for the visual mood it produces, with a     ║
║  coherent palette across primary, accent, success, warning, error,       ║
║  background, surface, and panel. The full color spectrum is covered     ║
║  (warm / cool / nature / mono).                                         ║
║                                                                           ║
║  Naming convention:                                                      ║
║                                                                           ║
║    All custom themes are prefixed with 'aria-' so they sort together    ║
║    in the picker and never collide with Textual's built-ins.            ║
║                                                                           ║
║  Aesthetic guarantees (informal but enforced by review):                ║
║                                                                           ║
║    • Foreground/background contrast ≥ 4.5:1 (WCAG AA) for body text     ║
║    • Each theme's accent is visibly distinct from its primary           ║
║    • success/warning/error are differentiable even in monochrome       ║
║      colorblind sims (we use luminance shifts, not just hue)            ║
║    • Dark themes have luminosity_spread ≥ 0.20 so $surface lifts        ║
║      visibly from $background                                            ║
║                                                                           ║
║  Adding a new theme:                                                     ║
║                                                                           ║
║    1. Append a CockpitTheme dataclass instance to CURATED_THEMES below. ║
║    2. Run the cockpit; pick the new theme from the menu.                ║
║    3. If colors feel off, adjust HEX values (no recompile needed —     ║
║       cockpit picks them up on next launch).                            ║
║    4. Run tests/test_themes.py to verify contrast invariants hold.      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App


@dataclass(frozen=True)
class CockpitTheme:
    """A curated theme spec. Maps cleanly to textual.theme.Theme on register."""
    name: str                  # 'aria-ember', 'aria-cobalt', etc.
    family: str                # 'warm' | 'cool' | 'nature' | 'mono' | 'spectrum'
    mood: str                  # one-line vibe description
    dark: bool
    background: str
    surface: str
    panel: str
    primary: str               # main brand color (titles, focused borders)
    accent: str                # secondary highlight (active selections, callouts)
    secondary: str             # tertiary (subtle accents, dividers)
    success: str
    warning: str
    error: str
    foreground: str | None = None  # body text; None → textual default ($foreground)
    boost: str | None = None       # subtle additional accent
    luminosity_spread: float = 0.20
    text_alpha: float = 0.95
    # Effects slot for special behaviors (hue cycling, breathing, etc.).
    # Empty dict for ordinary themes; populated for special ones like aria-prism.
    effects: dict = field(default_factory=dict)

    def to_textual_theme(self):
        """Convert to a textual.theme.Theme instance.

        IMPORTANT: We do NOT pass family/mood through `variables`. Textual
        treats every `variables` entry as a CSS value to be inlined into
        the stylesheet — and our mood strings contain prose like
        "deep water; signal carrying clean". The semicolon makes the CSS
        parser think a rule has ended, then it errors on the next word.
        family/mood live as dataclass fields on CockpitTheme for our own
        grouping/display, never as Textual variables.
        """
        from textual.theme import Theme
        return Theme(
            name=self.name,
            primary=self.primary,
            secondary=self.secondary,
            warning=self.warning,
            error=self.error,
            success=self.success,
            accent=self.accent,
            foreground=self.foreground,
            background=self.background,
            surface=self.surface,
            panel=self.panel,
            boost=self.boost,
            dark=self.dark,
            luminosity_spread=self.luminosity_spread,
            text_alpha=self.text_alpha,
        )


# ─── The Spectrum ──────────────────────────────────────────────────────────
#
# 16 themes. Each one's palette is hand-tuned, not generated by hue rotation.
# Test each in the cockpit; aesthetics matter.

CURATED_THEMES: list[CockpitTheme] = [
    # ─── WARM ──────────────────────────────────────────────────────────────
    CockpitTheme(
        name="aria-ember",
        family="warm",
        mood="banked coals; a forge at rest",
        dark=True,
        background="#1A0E0A",
        surface="#241410",
        panel="#2E1A14",
        primary="#FF7849",       # ember orange
        accent="#FFB347",        # firelight gold
        secondary="#C44C2E",     # deep ember
        success="#A3B86C",       # smoke-green
        warning="#F4C430",       # spark yellow
        error="#E63946",         # arterial red
        foreground="#F2E8DE",
    ),
    CockpitTheme(
        name="aria-sunset",
        family="warm",
        mood="last light over a calm horizon",
        dark=True,
        background="#1B1428",
        surface="#2A1F35",
        panel="#352948",
        primary="#FF8C42",       # sunset orange
        accent="#FFD56B",         # golden hour
        secondary="#D65780",     # purpled rose
        success="#7FBC8C",
        warning="#F2A65A",
        error="#E84855",
        foreground="#F4EDE4",
    ),
    CockpitTheme(
        name="aria-gold",
        family="warm",
        mood="illuminated manuscript; quiet wealth",
        dark=True,
        background="#1A150A",
        surface="#231D10",
        panel="#2E2516",
        primary="#D4AF37",       # heraldic gold
        accent="#F0CF65",         # gilded edge
        secondary="#8B6F2A",     # antique brass
        success="#9CB071",
        warning="#E5B748",
        error="#B0413E",
        foreground="#F5EDD6",
    ),
    CockpitTheme(
        name="aria-amber",
        family="warm",
        mood="amber preserved; warm clarity",
        dark=True,
        background="#1F1605",
        surface="#2B2009",
        panel="#382B10",
        primary="#FFB000",       # bright amber
        accent="#FFCB47",
        secondary="#C77C28",
        success="#8FAE5D",
        warning="#FFD23F",
        error="#D5453A",
        foreground="#F8EDC9",
    ),
    CockpitTheme(
        name="aria-rose",
        family="warm",
        mood="petals at dusk; tender precision",
        dark=True,
        background="#1F1318",
        surface="#2B1A22",
        panel="#36222D",
        primary="#E76F94",       # rose
        accent="#F0A4B9",
        secondary="#A84B70",     # deep rose
        success="#A3B86C",
        warning="#F2C14E",
        error="#D64550",
        foreground="#F4E6EB",
    ),
    CockpitTheme(
        name="aria-crimson",
        family="warm",
        mood="red ink on vellum; declarative",
        dark=True,
        background="#1A0809",
        surface="#240E0F",
        panel="#2F1416",
        primary="#DC143C",       # crimson
        accent="#FF6B6B",
        secondary="#8B1A1A",
        success="#7FBC8C",
        warning="#F2C14E",
        error="#FF3838",
        foreground="#F2E0DD",
    ),

    # ─── COOL ──────────────────────────────────────────────────────────────
    CockpitTheme(
        name="aria-cobalt",
        family="cool",
        mood="deep water; signal carrying clean",
        dark=True,
        background="#0A1626",
        surface="#0F1E33",
        panel="#152741",
        primary="#3D7EFF",       # cobalt blue
        accent="#5FB1FF",
        secondary="#1F4E8A",
        success="#5FB389",
        warning="#F2C14E",
        error="#E63946",
        foreground="#E1ECF7",
    ),
    CockpitTheme(
        name="aria-cyan",
        family="cool",
        mood="phosphor cathode-ray; precise",
        dark=True,
        background="#071417",
        surface="#0C1E22",
        panel="#10282E",
        primary="#22D3EE",       # cyan
        accent="#67E8F9",
        secondary="#0E7490",
        success="#86EFAC",
        warning="#F2C14E",
        error="#F87171",
        foreground="#E0F2F1",
    ),
    CockpitTheme(
        name="aria-indigo",
        family="cool",
        mood="ink at midnight; deliberate",
        dark=True,
        background="#0F0F1F",
        surface="#16162E",
        panel="#1F1F3D",
        primary="#7C7DFF",       # indigo
        accent="#A0A8FF",
        secondary="#4747A8",
        success="#6BCB77",
        warning="#FFD23F",
        error="#FF6B6B",
        foreground="#E5E5F5",
    ),
    CockpitTheme(
        name="aria-violet",
        family="cool",
        mood="purple velvet; contemplative",
        dark=True,
        background="#150F1F",
        surface="#1F1530",
        panel="#291D40",
        primary="#B084FF",       # violet
        accent="#D4B5FF",
        secondary="#6B3FA0",
        success="#7FBC8C",
        warning="#F2C14E",
        error="#E84855",
        foreground="#EFE6F8",
    ),
    CockpitTheme(
        name="aria-mint",
        family="cool",
        mood="cool morning glass; awake",
        dark=False,
        background="#F1F8F5",
        surface="#E4F1EB",
        panel="#D5E9DF",
        primary="#10B981",       # mint
        accent="#34D399",
        secondary="#047857",
        success="#16A34A",
        warning="#D97706",
        error="#DC2626",
        foreground="#062E2B",
    ),

    # ─── NATURE ────────────────────────────────────────────────────────────
    CockpitTheme(
        name="aria-forest",
        family="nature",
        mood="canopy at dusk; sheltering",
        dark=True,
        background="#0C1410",
        surface="#121E16",
        panel="#1A2A1E",
        primary="#52B788",       # forest green
        accent="#95D5B2",
        secondary="#2D6A4F",
        success="#74C69D",
        warning="#F2C14E",
        error="#D7263D",
        foreground="#E8F1E8",
    ),
    CockpitTheme(
        name="aria-sage",
        family="nature",
        mood="dried herbs in a south window",
        dark=False,
        background="#F6F4EE",
        surface="#EBE7DC",
        panel="#DDD7C8",
        primary="#6B8E5A",       # sage
        accent="#A4B494",
        secondary="#4A6741",
        success="#6B8E5A",
        warning="#C09553",
        error="#A0344C",
        foreground="#2C2F2A",
    ),
    CockpitTheme(
        name="aria-olive",
        family="nature",
        mood="weathered patina; durable",
        dark=True,
        background="#15170D",
        surface="#1F2113",
        panel="#2A2C1C",
        primary="#9ACD32",       # olive-yellow
        accent="#C5E063",
        secondary="#556B2F",
        success="#7FB069",
        warning="#E5B748",
        error="#BC4749",
        foreground="#EFEEC8",
    ),

    # ─── MONO ──────────────────────────────────────────────────────────────
    CockpitTheme(
        name="aria-slate",
        family="mono",
        mood="overcast; neutral and steady",
        dark=True,
        background="#10141A",
        surface="#181D24",
        panel="#222831",
        primary="#94A3B8",       # slate
        accent="#CBD5E1",
        secondary="#475569",
        success="#4ADE80",
        warning="#FACC15",
        error="#F87171",
        foreground="#E2E8F0",
    ),
    CockpitTheme(
        name="aria-paper",
        family="mono",
        mood="rag paper under a reading lamp",
        dark=False,
        background="#FAF7F0",
        surface="#F1ECE0",
        panel="#E5DECF",
        primary="#2D2A26",       # ink
        accent="#7C6F57",
        secondary="#A39B86",
        success="#3B7A3B",
        warning="#A86A1A",
        error="#A8261C",
        foreground="#2D2A26",
    ),

    # ─── SPECTRUM ──────────────────────────────────────────────────────────
    # Special: hue-cycling themes. The static palette below is the starting
    # frame; the HueCycleEngine in cockpit/hue_cycle.py rotates the rotatable
    # slots around the color wheel while the cockpit runs.
    #
    # background/surface/panel and the semantic colors (success/warning/error)
    # never cycle — readability and semantic stability are sacred.
    #
    # Kill switch for both: SOV_NO_HUE_CYCLE=1 env var.

    CockpitTheme(
        name="aria-prism",
        family="spectrum",
        mood="light through glass; primary, accent, and secondary trace different orbits",
        dark=True,
        background="#0F0F14",
        surface="#16161E",
        panel="#1F1F2A",
        primary="#FF6B9D",       # starting hue: rose-pink
        accent="#7DD3FC",        # starting hue: sky-blue
        secondary="#A78BFA",     # starting hue: lavender
        success="#86EFAC",       # static (semantic stability)
        warning="#FCD34D",
        error="#FB7185",
        foreground="#F0F0F5",
        effects={
            "hue_cycle": {
                "period_seconds": 180,   # 3 minutes for primary's full rotation
                "tick_seconds": 2,        # 90 frames per cycle — smooth
                "amplitude": 1.0,
                "rotate_slots": ["primary", "accent", "secondary"],
                # Differential rotation — the magic. Each slot moves at
                # its own rate, some inverse. The cockpit feels like
                # refraction, not a metronome.
                "slot_speeds": {
                    "primary":    1.0,     # full forward at base speed
                    "accent":     0.7,     # 70% speed — slowly out of sync
                    "secondary": -1.3,     # opposite direction, 30% faster
                },
            }
        },
    ),
    CockpitTheme(
        name="aria-aurora",
        family="spectrum",
        mood="northern lights drifting across glacier ice",
        dark=True,
        background="#070C14",
        surface="#0C141F",
        panel="#121C2B",
        primary="#5EEAD4",       # starting: aurora-teal
        accent="#A78BFA",         # starting: violet
        secondary="#86EFAC",     # starting: ice-green
        success="#86EFAC",
        warning="#FCD34D",
        error="#FB7185",
        foreground="#E0F2F1",
        effects={
            "hue_cycle": {
                "period_seconds": 360,   # 6 minutes — much slower than prism
                "tick_seconds": 3,
                "amplitude": 0.35,        # 0.35 = stay in cool/aurora hues
                "rotate_slots": ["primary", "accent", "secondary"],
                # Subtle differential. Aurora drifts; it doesn't dance.
                "slot_speeds": {
                    "primary":    1.0,
                    "accent":     0.5,
                    "secondary": -0.7,
                },
            },
            # Per-theme ripple tuning (read by RippleFrame / rippling GlyphStage):
            # a long, slow wave that suits the aurora's drifting palette.
            "ripple": {
                "color_slot": "primary",
                "wavelen": 64.0,
                "speed": 16.0,
                "amplitude": 0.58,
                "midpoint": 0.62,
            },
        },
    ),
    # ─── v0.2.46 "Living Frame" additions ─────────────────────────────────
    # A calm normal theme tuned to pair with the Aurora Heart, and a
    # hue-cycling special theme tuned to pair with the rippling RippleFrame.
    CockpitTheme(
        name="aria-rose-quartz",
        family="warm",
        mood="soft stone; a kept heart, unhurried",
        dark=True,
        background="#140E14",
        surface="#1D141E",
        panel="#271A28",
        primary="#F7A8C4",       # rose quartz
        accent="#C9A7F5",         # lavender light
        secondary="#8E6FB0",     # muted violet
        success="#9BD0A8",
        warning="#F4C97A",
        error="#F07A8C",
        foreground="#F4E9F0",
    ),
    CockpitTheme(
        name="aria-nebula",
        family="spectrum",
        mood="deep field; colour drifting through dust and starlight",
        dark=True,
        background="#06060F",
        surface="#0C0B1A",
        panel="#141229",
        primary="#7C6CFF",       # starting: indigo
        accent="#FF6BD0",         # starting: nebula magenta
        secondary="#58E0E6",     # starting: ion cyan
        success="#86EFAC",
        warning="#FCD34D",
        error="#FB7185",
        foreground="#E6E3F5",
        effects={
            "hue_cycle": {
                "period_seconds": 300,   # 5 minutes — a slow cosmic drift
                "tick_seconds": 3,
                "amplitude": 0.6,         # wider than aurora: roams the wheel
                "rotate_slots": ["primary", "accent", "secondary"],
                "slot_speeds": {
                    "primary":    1.0,
                    "accent":    -0.6,
                    "secondary":  0.4,
                },
            },
            # Nebula's frame rides the magenta accent on a medium wave.
            "ripple": {
                "color_slot": "accent",
                "wavelen": 56.0,
                "speed": 20.0,
                "amplitude": 0.66,
                "midpoint": 0.60,
            },
        },
    ),
    # ─── v0.2.47 "Spectrum" — the full rainbow theme ──────────────────────
    # Everything cycles through a smooth hue: primary/accent/secondary AND the
    # structural surfaces (background/surface/panel) — the latter kept dark by a
    # lightness cap so the whole field drifts in colour while staying readable.
    # Foreground + semantic colours (success/warning/error) stay fixed. Every
    # border is the Aurora rainbow-ripple, and the status-bar heart cycles too.
    CockpitTheme(
        name="aria-rainbow",
        family="spectrum",
        mood="everything, in every colour, always becoming",
        dark=True,
        background="#0E0820",    # dark + saturated indigo → hue rotation reads
        surface="#160B2A",
        panel="#1E1138",
        primary="#FF5D8F",       # starting: rose
        accent="#5DE2FF",         # starting: cyan
        secondary="#B68CFF",     # starting: violet
        success="#86EFAC",        # fixed (semantic)
        warning="#FCD34D",        # fixed (semantic)
        error="#FB7185",          # fixed (semantic — stays red)
        foreground="#F0ECF7",     # fixed (readable text)
        effects={
            "hue_cycle": {
                "period_seconds": 90,        # one full, gentle rotation ≈ 90s
                "tick_seconds": 2,
                "amplitude": 1.0,
                "allow_background": True,     # the whole field drifts…
                "background_max_lightness": 0.16,  # …kept dark but now visible
                "rotate_slots": [
                    "primary", "accent", "secondary",
                    "background", "surface", "panel",
                ],
                "slot_speeds": {
                    "primary":    1.0,
                    "accent":    -0.7,
                    "secondary":  0.5,
                    "background": 0.3,   # surfaces drift slowly, calmly
                    "surface":    0.3,
                    "panel":      0.4,
                },
            },
            # Every border becomes the Aurora rainbow-ripple.
            "ripple": {
                "hue_cycle": True,
                "hue_period": 11.0,
                "hue_spread": 1.0,
                "amplitude": 0.5,
                "midpoint": 0.72,
            },
            # And the status-bar heart cycles through the spectrum too.
            "rainbow_heart": True,
        },
    ),
]


# ─── Registration ─────────────────────────────────────────────────────────

def register_curated_themes(app: "App") -> list[str]:
    """Register every curated theme on the given Textual app.

    Returns the list of theme names that were successfully registered.
    Idempotent: re-registering a theme replaces the prior definition.
    """
    registered: list[str] = []
    for spec in CURATED_THEMES:
        try:
            app.register_theme(spec.to_textual_theme())
            registered.append(spec.name)
        except Exception:
            # If textual changes the register_theme contract, we'd rather
            # ship without the missing themes than crash the cockpit.
            continue
    return registered


def get_theme_by_name(name: str) -> CockpitTheme | None:
    """Look up a curated theme spec by its name."""
    for t in CURATED_THEMES:
        if t.name == name:
            return t
    return None


def themes_by_family() -> dict[str, list[CockpitTheme]]:
    """Group curated themes by family for display purposes."""
    out: dict[str, list[CockpitTheme]] = {}
    for t in CURATED_THEMES:
        out.setdefault(t.family, []).append(t)
    return out


__all__ = [
    "CockpitTheme",
    "CURATED_THEMES",
    "register_curated_themes",
    "get_theme_by_name",
    "themes_by_family",
]
