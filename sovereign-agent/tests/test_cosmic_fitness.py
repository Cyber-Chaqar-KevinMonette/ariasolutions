"""
test_cosmic_fitness.py — tests for the v0.2.41 "Cosmic Fitness" visual gym.

Two layers, matching the house style:

  • Pure logic (no Textual): the width taxonomy, the curated inventory, the
    special-effects registry, the fitness report, and the verdict store. These
    are deterministic and fast.

  • Headless widget tests via Textual's App.run_test()/Pilot: the cockpit still
    renders, the inline glyph picker toggles and inserts, the CosmicFitnessScreen
    opens with the full inventory + live effects, picking a glyph inserts + closes,
    and the slash commands dispatch.

Nothing here needs a real terminal, an LLM, or a network — safe to run anywhere.
"""
from __future__ import annotations

import asyncio

import pytest

from sovereign_agent.cockpit import cosmic_fitness as cf
from sovereign_agent.cockpit import glyph_metrics as gm
from sovereign_agent.glyphs import is_width_safe

# ════════════════════════════════════════════════════════════════════════
#  Pure logic — taxonomy
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("char,expected", [
    ("\u2726", "safe"),          # ✦ four-pointed star (EAW=N, not emoji)
    ("\u2727", "safe"),          # ✧
    ("\u2738", "safe"),          # ✸ heavy eight-pointed (urgent fx)
    ("\u25C9", "safe"),          # ◉ fisheye
    ("\u2713", "safe"),          # ✓ check mark
    ("\u25CA", "safe"),          # ◊ lozenge
    ("\u2665", "convention"),    # ♥ heart suit (EAW=A, blessed)
    ("\u2500", "convention"),    # ─ box drawing (EAW=A, whitelisted)
    ("\u2588", "convention"),    # █ full block (EAW=A, now blessed)
    ("\u2764", "emoji"),         # ❤ heavy black heart — the trap
    ("\u2600", "emoji"),         # ☀ sun — emoji-variation base
    ("\u2714", "emoji"),         # ✔ heavy check — emoji-variation base
    ("\u25B6", "emoji"),         # ▶ right triangle — emoji-variation base
    ("\u2604", "emoji"),         # ☄ comet — emoji-variation base
    ("\U0001F496", "wide"),      # 💖 sparkling heart (EAW=W)
    ("\U0001F916", "wide"),      # 🤖 robot face
    ("\u2B50", "wide"),          # ⭐ white medium star (EAW=W)
    ("\u2764\uFE0F", "composite"),  # ❤️ heart + VS16
])
def test_classify_glyph(char, expected):
    status, eaw, name, cp = cf.classify_glyph(char)
    assert status == expected, f"{char!r} -> {status}, expected {expected}"
    assert cp.startswith("U+")


def test_emoji_class_is_not_layout_safe():
    # The whole point of the emoji class: it must NOT be treated as layout-safe.
    spec = cf._spec("\u2764", "heart", "Test")
    assert spec.status == "emoji"
    assert spec.is_width_safe is False


def test_composite_detects_vs16_and_zwj():
    s1, *_ = cf.classify_glyph("\u2764\uFE0F")        # VS16
    s2, *_ = cf.classify_glyph("\U0001F468\u200D\U0001F4BB")  # ZWJ man+laptop
    assert s1 == "composite" and s2 == "composite"


def test_status_badges_are_themselves_width_safe():
    # The legend must never be the thing that drifts.
    for badge in cf.STATUS_BADGE.values():
        assert is_width_safe(badge), f"status badge {badge!r} is not width-safe"


# ════════════════════════════════════════════════════════════════════════
#  Pure logic — inventory
# ════════════════════════════════════════════════════════════════════════

def test_curated_categories_nonempty_and_consistent():
    cats = cf.curated_categories()
    assert len(cats) >= 6
    for cat in cats:
        assert cat.glyphs, f"category {cat.name} is empty"
        for spec in cat.glyphs:
            # stored status must equal a fresh classification (no drift)
            fresh, *_ = cf.classify_glyph(spec.char)
            assert spec.status == fresh, (
                f"{spec.codepoint} stored {spec.status}, reality {fresh}"
            )
            # width-safety helper agrees with status
            assert spec.is_width_safe == (spec.status in ("safe", "convention"))


def test_quick_picker_specs():
    specs = cf.quick_picker_specs()
    assert len(specs) >= 20
    # every spec carries the derived fields
    for s in specs:
        assert s.char and s.codepoint and s.unicode_name


def test_wide_and_composite_get_alternatives_where_known():
    # a few well-known ones should resolve to a one-cell (safe/convention) glyph
    assert cf.safe_alternative_for("\U0001F496") == "\u2665"   # 💖 → ♥
    assert cf.safe_alternative_for("\u2B50") == "\u2726"        # ⭐ → ✦
    assert cf.safe_alternative_for("\u2764\uFE0F") == "\u2665"  # ❤️ → ♥
    assert cf.safe_alternative_for("\u2764") == "\u2665"        # ❤ → ♥
    # the alternative itself must render one cell (safe OR blessed-convention)
    for src in ("\U0001F496", "\u2B50", "\u2764\uFE0F", "\u2764"):
        alt = cf.safe_alternative_for(src)
        assert alt is not None
        assert cf.classify_glyph(alt)[0] in ("safe", "convention")


# ════════════════════════════════════════════════════════════════════════
#  Pure logic — special effects
# ════════════════════════════════════════════════════════════════════════

def test_every_special_effect_glyph_is_layout_safe():
    # An effect animates in a width-counted row, so its glyph must be truly
    # one-cell: classification safe OR convention (not merely EAW-narrow, and
    # never the emoji trap). This is the stricter rule that catches ❤/▶/☄.
    fx = cf.special_effects()
    assert len(fx) >= 6
    for e in fx:
        status, *_ = cf.classify_glyph(e.glyph)
        assert status in ("safe", "convention"), (
            f"effect {e.label} uses {e.glyph!r} classified '{status}'"
        )


def test_effect_configs_are_valid():
    for e in cf.special_effects():
        c = e.config
        assert c.period_seconds > 0
        assert c.tick_seconds > 0
        assert 0.0 <= c.amplitude <= 1.0
        assert 0.0 <= c.midpoint <= 1.0
        if e.kind == "ripple":
            assert e.length >= 2


def test_effect_lookup_by_key():
    assert cf.effect_by_key("heartbeat") is not None
    assert cf.effect_by_key("nope") is None


# ════════════════════════════════════════════════════════════════════════
#  Pure logic — fitness report
# ════════════════════════════════════════════════════════════════════════

def test_fitness_report_passes_clean():
    r = cf.run_cosmic_fitness(include_scan=False)
    assert r.passed, r.render_text()
    assert r.effects_ok and r.consistency_ok and r.animations_ok
    assert r.total_glyphs == (
        r.safe + r.convention + r.emoji + r.wide + r.composite
    )
    assert r.grade == "STRONG"
    # report renders without error and mentions the sections
    text = r.render_text()
    assert "glyph inventory" in text and "special effects" in text
    assert "glyph animations" in text


def test_report_has_emoji_class_count():
    r = cf.run_cosmic_fitness(include_scan=False)
    # the curated palette includes ❤ and friends, so emoji count is > 0
    assert r.emoji > 0
    assert "emoji" in r.summary


def test_fitness_report_with_scan_is_informational_only():
    r = cf.run_cosmic_fitness(include_scan=True)
    # scan findings never flip the pass verdict
    assert r.passed
    assert r.scanned_files >= 0


# ════════════════════════════════════════════════════════════════════════
#  Pure logic — verdict store
# ════════════════════════════════════════════════════════════════════════

def test_verdict_store_roundtrip(tmp_path):
    store = cf.GlyphVerdictStore(tmp_path)
    store.record("\U0001F496", "replace", "too sparkly for the title bar")
    store.record("\u2764", "good")
    store.record("\u2764\uFE0F", "remove", "VS16 breaks alignment")

    assert store.summary() == {"total": 3, "good": 1, "replace": 1, "remove": 1}
    rec = store.get("\U0001F496")
    assert rec["verdict"] == "replace"
    assert rec["suggested_alternative"] == "\u2665"   # 💖 → ♥ (one-cell heart)

    # survives a fresh instance (persistence)
    store2 = cf.GlyphVerdictStore(tmp_path)
    assert store2.summary()["total"] == 3
    assert store2.by_verdict("remove")[0]["char"] == "\u2764\uFE0F"

    # clear works
    assert store2.clear("\u2764") is True
    assert store2.summary()["total"] == 2


def test_verdict_store_rejects_bad_verdict(tmp_path):
    store = cf.GlyphVerdictStore(tmp_path)
    with pytest.raises(ValueError):
        store.record("\u2764", "maybe")  # type: ignore[arg-type]


def test_kill_switch(monkeypatch):
    assert cf.cosmic_fitness_enabled() is True
    monkeypatch.setenv(cf.KILL_SWITCH_ENV, "1")
    assert cf.cosmic_fitness_enabled() is False


# ════════════════════════════════════════════════════════════════════════
#  Headless widget tests
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cockpit_still_renders_with_cosmic_wired():
    """Regression: the cockpit launches, and the ◊ cosmic entry is reachable.

    menu-split-2-d (Kevin's rule): the ⚙ menu is Settings + Help only, so
    cosmic lives in the ☰ commands popup (everything else). This opens that
    popup to find the cosmic button.
    """
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#chat-log") is not None
        assert app.query_one("#input-box") is not None
        app.action_command_palette()
        await pilot.pause()
        cosmic = [b for b in app.screen.query(CommandButton)
                  if b.palette_cmd.key == "cosmic"]
        assert cosmic, "the ◊ cosmic entry should be in the ☰ commands popup"
        app.action_command_palette()   # toggle closes it
        await pilot.pause()
        # inline picker is present but hidden by default
        picker = app.query_one("#glyph-picker")
        assert picker.display is False


@pytest.mark.asyncio
async def test_inline_picker_toggles_and_inserts():
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import GlyphButton
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        picker = app.query_one("#glyph-picker")
        assert picker.display is False

        app.action_toggle_glyphs()
        await pilot.pause()
        assert picker.display is True

        pbtns = [b for b in app.query(GlyphButton) if not b.in_modal]
        assert len(pbtns) >= 20

        inp = app.query_one("#input-box", Input)
        inp.value = ""
        app.on_button_pressed(Button.Pressed(pbtns[0]))
        await pilot.pause()
        assert pbtns[0].spec.char in inp.value
        # inline picker stays open for rapid expression
        assert picker.display is True

        # toggling again hides it
        app.action_toggle_glyphs()
        await pilot.pause()
        assert picker.display is False


@pytest.mark.asyncio
async def test_cosmic_modal_opens_with_inventory_and_live_effects():
    from sovereign_agent.cockpit import CockpitApp, CosmicFitnessScreen
    from sovereign_agent.cockpit.app import GlyphButton
    from sovereign_agent.cockpit.breathing_glyph import BreathingBorder
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_cosmic_fitness()
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, CosmicFitnessScreen)

        # full inventory present in the modal
        mbtns = list(app.screen.query(GlyphButton))
        assert len(mbtns) >= 50

        # all special effects are live (real animated widgets)
        live = list(app.screen.query(BreathingBorder))
        assert len(live) == len(cf.special_effects())

        # Esc closes
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CosmicFitnessScreen)


@pytest.mark.asyncio
async def test_modal_glyph_pick_inserts_and_closes():
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp, CosmicFitnessScreen
    from sovereign_agent.cockpit.app import GlyphButton
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_cosmic_fitness()
        await pilot.pause()
        await pilot.pause()
        inp = app.query_one("#input-box", Input)
        inp.value = ""
        target = list(app.screen.query(GlyphButton))[0]
        app.screen.on_button_pressed(Button.Pressed(target))
        await pilot.pause()
        assert not isinstance(app.screen, CosmicFitnessScreen)
        assert target.spec.char in inp.value


@pytest.mark.asyncio
async def test_cosmic_slash_commands():
    from textual.widgets import Input

    from sovereign_agent.cockpit import CockpitApp, CosmicFitnessScreen
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        inp = app.query_one("#input-box", Input)

        # /cosmic opens the modal
        app.on_input_submitted(Input.Submitted(inp, "/cosmic", validation_result=None))
        await pilot.pause()
        assert isinstance(app.screen, CosmicFitnessScreen)
        await pilot.press("escape")
        await pilot.pause()

        # /pick toggles the inline picker
        picker = app.query_one("#glyph-picker")
        assert picker.display is False
        app.on_input_submitted(Input.Submitted(inp, "/pick", validation_result=None))
        await pilot.pause()
        assert picker.display is True

        # /cosmic report prints inline without error (chat log grows)
        chat = app.query_one("#chat-log")
        before = len(chat.lines)
        app.on_input_submitted(
            Input.Submitted(inp, "/cosmic report", validation_result=None)
        )
        await pilot.pause()
        assert len(chat.lines) > before


@pytest.mark.asyncio
async def test_cosmic_mark_slash_records_verdict():
    from textual.widgets import Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS
    # The config system already sandboxes data_dir to a temp path under test,
    # so we read the real one the app uses rather than patching a frozen field.
    data_dir = SETTINGS.paths.data_dir
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        inp = app.query_one("#input-box", Input)
        app.on_input_submitted(Input.Submitted(
            inp, "/cosmic mark \U0001F496 replace too sparkly",
            validation_result=None,
        ))
        await pilot.pause()
        store = cf.GlyphVerdictStore(data_dir)
        rec = store.get("\U0001F496")
        assert rec is not None and rec["verdict"] == "replace"
        # clean up so we never leave a verdict behind in a shared dir
        store.clear("\U0001F496")


# ════════════════════════════════════════════════════════════════════════
#  Animations catalog (pure logic)
# ════════════════════════════════════════════════════════════════════════

def test_animation_catalog_valid():
    anims = cf.animations()
    assert len(anims) >= 6
    for a in anims:
        assert a.frames, f"{a.key} has no frames"
        assert a.fps > 0
        assert a.interval > 0
        # tier is consistent with the frames
        if a.is_layout_safe:
            assert a.tier == "layout-safe"
            for f in a.frames:
                assert cf.classify_glyph(f)[0] in ("safe", "convention")
        else:
            assert a.tier == "sandbox-only"


def test_canonical_layout_safe_animations_stay_safe():
    # the regression guard: these keys must remain one-cell on every frame
    for key in ("spinner", "orbit", "pulse", "bar", "ring", "twinkle"):
        a = cf.animation_by_key(key)
        assert a is not None, f"missing animation {key}"
        assert a.is_layout_safe, f"{key} drifted to sandbox-only!"


def test_sandbox_animations_are_flagged():
    for key in ("moon", "dance", "sparkle"):
        a = cf.animation_by_key(key)
        assert a is not None
        assert not a.is_layout_safe
        assert a.worst_status in ("emoji", "wide", "composite")


def test_animation_validation_in_report():
    r = cf.run_cosmic_fitness(include_scan=False)
    assert r.animations_ok
    assert r.animations_total == len(cf.animations())
    assert r.animations_layout_safe >= 6
    assert r.animations_sandbox >= 1


# ════════════════════════════════════════════════════════════════════════
#  AnimatedGlyph widget
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_animated_glyph_layout_safe_runs():
    from textual.app import App
    from textual.widgets import Static

    from sovereign_agent.cockpit.animated_glyph import AnimatedGlyph

    spinner = cf.animation_by_key("spinner")

    class _A(App):
        def compose(self):
            yield AnimatedGlyph(spinner, id="anim")
            yield Static("sentinel", id="sentinel")

    app = _A()
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one("#anim", AnimatedGlyph)
        assert w.is_animating
        first = w.current_frame
        await asyncio.sleep(0.3)
        await pilot.pause()
        # frame advanced
        assert w.current_frame != first or len(spinner.frames) == 1


@pytest.mark.asyncio
async def test_animated_glyph_rejects_sandbox_without_flag():
    from sovereign_agent.cockpit.animated_glyph import AnimatedGlyph
    dance = cf.animation_by_key("dance")
    # sandbox-only animation must refuse to run unboxed
    with pytest.raises(ValueError):
        AnimatedGlyph(dance)
    # but is allowed with the explicit informed-caller flag
    w = AnimatedGlyph(dance, assume_width_safe=True)
    assert w is not None


@pytest.mark.asyncio
async def test_animated_glyph_reduced_motion(monkeypatch):
    from textual.app import App

    from sovereign_agent.cockpit.animated_glyph import AnimatedGlyph
    monkeypatch.setenv("SOV_REDUCED_MOTION", "1")
    spinner = cf.animation_by_key("spinner")

    class _A(App):
        def compose(self):
            yield AnimatedGlyph(spinner, id="anim")

    app = _A()
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one("#anim", AnimatedGlyph)
        # reduced motion: no timer, holds a single frame
        assert not w.is_animating


# ════════════════════════════════════════════════════════════════════════
#  GlyphStage — the isolation invariant
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_glyph_stage_pins_its_own_width_regardless_of_content():
    from textual.app import App
    from textual.widgets import Static

    from sovereign_agent.cockpit.glyph_stage import GlyphStage

    class _A(App):
        def compose(self):
            stage = GlyphStage(cells=10, id="stage")
            with stage:
                # absurdly wide content that would blow out a naive container
                yield Static("\U0001F496" * 200 + "wide" * 50)

    app = _A()
    async with app.run_test() as pilot:
        await pilot.pause()
        stage = app.query_one("#stage", GlyphStage)
        # outer width is pinned to cells + border (10 + 2), NOT grown to content
        assert stage.outer_size.width == 12, (
            f"stage grew to {stage.outer_size.width}; isolation broken"
        )


@pytest.mark.asyncio
async def test_glyph_stage_does_not_shift_a_sibling():
    """The core promise: wide content inside a stage cannot move the geometry
    of widgets outside it. We compare a sibling's x-offset with the stage empty
    vs. stuffed with wide emoji — it must not move."""
    from textual.app import App
    from textual.containers import Horizontal
    from textual.widgets import Static

    from sovereign_agent.cockpit.glyph_stage import GlyphStage

    class _A(App):
        wide: bool = False

        def compose(self):
            with Horizontal():
                stage = GlyphStage(cells=8, id="stage")
                with stage:
                    yield Static(("\U0001F496\u2B50" * 40) if self.wide else "·")
                yield Static("SIB", id="sib")

    # empty-ish stage
    app1 = _A()
    async with app1.run_test() as pilot:
        await pilot.pause()
        x_empty = app1.query_one("#sib", Static).region.x

    # stuffed stage
    app2 = _A()
    app2.wide = True
    async with app2.run_test() as pilot:
        await pilot.pause()
        x_full = app2.query_one("#sib", Static).region.x

    assert x_empty == x_full, (
        f"sibling moved from x={x_empty} to x={x_full} when the stage was "
        f"filled with wide glyphs — isolation broken"
    )


# ════════════════════════════════════════════════════════════════════════
#  breathing_glyph escape hatch (blessed-narrow glyphs)
# ════════════════════════════════════════════════════════════════════════

def test_breathing_border_escape_hatch():
    from sovereign_agent.cockpit.breathing_glyph import BreathingBorder
    # ♥ is EAW-ambiguous, so the default guard rejects it…
    with pytest.raises(ValueError):
        BreathingBorder(glyph="\u2665")
    # …but an informed caller may opt out (it's blessed-narrow / one cell)
    w = BreathingBorder(glyph="\u2665", assume_width_safe=True)
    assert w is not None
    # genuinely wide emoji is still rejected by default
    with pytest.raises(ValueError):
        BreathingBorder(glyph="\U0001F496")


@pytest.mark.asyncio
async def test_modal_shows_animations_and_sandbox():
    from sovereign_agent.cockpit import CockpitApp, CosmicFitnessScreen
    from sovereign_agent.cockpit.animated_glyph import AnimatedEffect, AnimatedGlyph
    from sovereign_agent.cockpit.glyph_stage import GlyphStage
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_cosmic_fitness()
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, CosmicFitnessScreen)
        anims = list(app.screen.query(AnimatedGlyph))
        fx = list(app.screen.query(AnimatedEffect))
        stages = list(app.screen.query(GlyphStage))
        # 6 universal animations in the showcase + 2 in the stage
        assert len(anims) >= 7
        # 3 universal animated effects in the showcase + 1 in the stage
        # (ambiguous-width effects like `beat` are listed as text, not rendered)
        assert len(fx) >= 4
        assert len(stages) >= 1
        # CRITICAL (v0.2.45): every glyph rendered live in the bordered modal
        # must be UNIVERSAL one-cell width — not merely layout-safe — so no
        # frame can shift a border on any terminal (the ring/dancer jitter).
        assert all(w._spec.is_universal for w in anims), \
            "a non-universal animation is rendered live in the modal"
        assert all(w._spec.is_universal for w in fx), \
            "a non-universal animated effect is rendered live in the modal"
        await pilot.press("escape")
        await pilot.pause()


# ════════════════════════════════════════════════════════════════════════
#  Animated special effects (frames + glow/hue)
# ════════════════════════════════════════════════════════════════════════

def test_animated_effects_catalog_valid():
    aes = cf.animated_effects()
    assert len(aes) >= 4
    for ae in aes:
        assert ae.frames
        assert ae.frame_fps > 0
        assert 0.0 <= ae.amplitude <= 1.0
        assert 0.0 <= ae.midpoint <= 1.0
        assert ae.mode in ("glow", "hue")


def test_beating_heart_is_layout_safe_animated_effect():
    beat = cf.animated_effect_by_key("beat")
    assert beat is not None
    # ♥ and ♡ are both blessed-narrow → the beating heart runs anywhere
    assert beat.is_layout_safe
    assert beat.frames[-1] == "\u2661"   # rest beat is the open heart


def test_aurora_hue_actually_cycles():
    aurora = cf.animated_effect_by_key("aurora")
    assert aurora is not None and aurora.mode == "hue"
    c0 = cf.effect_color_at(aurora, 0.0)
    c_mid = cf.effect_color_at(aurora, aurora.hue_period / 2.0)
    assert c0 != c_mid, "hue should differ half-way through the cycle"


def test_glow_color_math_bounds():
    # blend extremes
    base, bg = (255, 0, 0), (0, 0, 0)
    assert cf.blend(base, bg, 1.0) == (255, 0, 0)
    assert cf.blend(base, bg, 0.0) == (0, 0, 0)
    # sine_alpha stays within [0,1]
    beat = cf.animated_effect_by_key("beat")
    for t in (0.0, 0.25, 0.5, 0.9, 3.3):
        a = cf.sine_alpha(t, beat.pulse_period, beat.amplitude, beat.midpoint)
        assert 0.0 <= a <= 1.0


def test_animated_effects_in_report():
    r = cf.run_cosmic_fitness(include_scan=False)
    assert r.animated_effects_ok
    assert r.animated_effects_total == len(cf.animated_effects())
    assert "animated special effects" in r.render_text()


@pytest.mark.asyncio
async def test_animated_effect_widget_runs_and_colors():
    from textual.app import App

    from sovereign_agent.cockpit.animated_glyph import AnimatedEffect
    beat = cf.animated_effect_by_key("beat")

    class _A(App):
        def compose(self):
            yield AnimatedEffect(beat, id="fx")

    app = _A()
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one("#fx", AnimatedEffect)
        assert w.is_animating
        await asyncio.sleep(0.3)
        await pilot.pause()
        # the displayed frame is always one of the spec's frames (markup is
        # consumed into styling; the colour maths are unit-tested separately)
        assert w.render().plain in beat.frames


@pytest.mark.asyncio
async def test_animated_effect_sandbox_requires_flag():
    from sovereign_agent.cockpit.animated_glyph import AnimatedEffect
    moon_glow = cf.animated_effect_by_key("moon_glow")
    assert moon_glow is not None and not moon_glow.is_layout_safe
    with pytest.raises(ValueError):
        AnimatedEffect(moon_glow)
    w = AnimatedEffect(moon_glow, assume_width_safe=True)
    assert w is not None


# ════════════════════════════════════════════════════════════════════════
#  Stable-render fix: inventory badges width-unstable glyphs (v0.2.43)
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_inventory_badges_unstable_glyphs_but_inserts_real_char():
    """The width-counted inventory grid must render only stable glyphs raw;
    emoji/wide/composite show their class badge instead — yet clicking still
    inserts the REAL glyph. This is what keeps borders from glitching on a
    terminal that draws those glyphs wider than Textual expects."""
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import GlyphButton
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_cosmic_fitness()
        await pilot.pause()
        await pilot.pause()
        btns = list(app.screen.query(GlyphButton))
        badged = [b for b in btns if getattr(b, "_badge_mode", False)]
        raw = [b for b in btns if not getattr(b, "_badge_mode", False)]
        assert badged and raw
        # every badged glyph is unstable; every raw glyph is stable
        assert all(b.spec.status not in ("safe", "convention") for b in badged)
        assert all(b.spec.status in ("safe", "convention") for b in raw)
        # a badged button's visible label is NOT the raw glyph
        b = badged[0]
        assert str(b.label) != b.spec.char
        # …but clicking it inserts the real character anyway
        inp = app.query_one("#input-box", Input)
        inp.value = ""
        app.screen.on_button_pressed(Button.Pressed(b))
        await pilot.pause()
        assert b.spec.char in inp.value


def test_status_badges_are_all_layout_safe():
    # Badges stand in for unstable glyphs, so they themselves must be one-cell.
    for st, badge in cf.STATUS_BADGE.items():
        assert cf.classify_glyph(badge)[0] in ("safe", "convention"), (
            f"badge {badge!r} for '{st}' is not layout-safe"
        )


# ════════════════════════════════════════════════════════════════════════
#  Universal-width distinction (the ring/dancer jitter fix)
# ════════════════════════════════════════════════════════════════════════

def test_universal_width_only_trusts_braille_box_block_ascii():
    for ch in ("\u2801", "\u2588", "\u2591", "\u2502", "A", " ", "\u2569"):
        assert cf.is_universal_width(ch), f"{ch!r} should be universal"
    # Ambiguous symbols are NOT universal — they are exactly the trap.
    for ch in ("\u2665", "\u25CF", "\u2605", "\u25C9", "\u25CB", "\u25C8",
               "\U0001F57A"):
        assert not cf.is_universal_width(ch), f"{ch!r} must not be universal"
    assert not cf.is_universal_width("")


def test_all_layout_safe_animations_are_universal():
    # After the rebuild, every animation we'd render live in the modal must be
    # universal — that is what stops the ring/twinkle from shifting a border.
    for an in cf.animations():
        if an.is_layout_safe:
            assert an.is_universal, f"animation {an.key!r} is layout-safe but not universal"


def test_ring_no_longer_uses_filled_circles():
    ring = cf.animation_by_key("ring")
    assert ring is not None and ring.is_universal
    # The old jitter came from ● (U+25CF) / ◉ (U+25C9); they must be gone.
    joined = "".join(ring.frames)
    assert "\u25CF" not in joined and "\u25C9" not in joined


def test_beat_effect_is_listed_not_universal():
    # The ♥/♡ beat stays in the catalog (valid where ♡ is one cell) but is NOT
    # universal, so the modal lists it as text rather than rendering it live.
    beat = cf.animated_effect_by_key("beat")
    assert beat is not None and beat.is_layout_safe and not beat.is_universal


# ════════════════════════════════════════════════════════════════════════
#  Glyph metrics — the width accounting system
# ════════════════════════════════════════════════════════════════════════
# The LIVE DSR probe and whether a Tier-2 override visually fixes rendering can
# only be validated on a real terminal — those are explicitly out of scope here.
# Everything testable without a TTY is covered below.

def test_dsr_column_parsing():
    assert gm.parse_dsr_column(b"\x1b[12;5R") == 5
    assert gm.parse_dsr_column(b"\x1b[1;1R") == 1
    # Takes the last reply if several arrive; ignores surrounding bytes.
    assert gm.parse_dsr_column(b"junk\x1b[2;3Rmore\x1b[9;7R") == 7
    assert gm.parse_dsr_column(b"no reply here") is None
    assert gm.parse_dsr_column(b"") is None


def test_width_table_roundtrip_and_merge():
    t = gm.WidthTable(term="cosmic")
    t.set("\U0001F57A", 2)
    t.set("A", 1)
    import json
    restored = gm.WidthTable.from_dict(json.loads(json.dumps(t.to_dict())))
    assert restored.widths == t.widths
    assert restored.term == "cosmic"
    assert restored.get("\U0001F57A") == 2
    other = gm.WidthTable(term="other")
    other.set("\u25CF", 2)
    merged = t.merge(other)
    assert merged.get("A") == 1 and merged.get("\u25CF") == 2
    # negative widths are rejected
    t.set("x", -1)
    assert "x" not in t


def test_overwide_glyphs_filters_by_threshold():
    t = gm.WidthTable()
    t.set("A", 1)
    t.set("\u2665", 1)
    t.set("\U0001F57A", 2)
    t.set("\u25CF", 3)
    assert gm.overwide_glyphs(t) == {"\U0001F57A", "\u25CF"}
    assert gm.overwide_glyphs(t, threshold=3) == {"\u25CF"}


def test_normalize_frames_pads_to_true_width():
    t = gm.WidthTable()
    t.set("\U0001F57A", 1)   # man dancing measured narrow
    t.set("\U0001F483", 2)   # woman dancing measured wide
    padded, target = gm.normalize_frames(("\U0001F57A", "\U0001F483"), t)
    assert target == 2
    assert padded[0] == "\U0001F57A "   # padded with one space → 2 true cells
    assert padded[1] == "\U0001F483"    # already 2 cells, untouched
    # With no measurements, falls back to width 1 (no padding).
    padded2, target2 = gm.normalize_frames(("a", "b"), gm.WidthTable())
    assert target2 == 1 and padded2 == ("a", "b")


def test_probe_returns_empty_without_tty():
    # The harness has no real TTY, so the probe must degrade to "measured
    # nothing" rather than hang or raise — the safety guarantee.
    table = gm.probe_terminal_widths(["A", "\u2665", "\U0001F57A"])
    assert len(table) == 0


def test_probe_disabled_by_kill_switch(monkeypatch):
    monkeypatch.setenv(gm.METRICS_KILL_ENV, "1")
    assert gm.metrics_enabled() is False
    assert len(gm.probe_terminal_widths(["A"])) == 0


def test_width_override_off_by_default():
    # Tier 2 must never engage without the explicit env opt-in.
    assert gm.width_override_allowed() is False
    t = gm.WidthTable()
    t.set("\U0001F57A", 1)
    try:
        # force=False + no env → refuses to install.
        assert gm.install_width_overrides(t) is False
    finally:
        gm.uninstall_width_overrides()


def test_width_override_install_and_uninstall_is_reversible():
    import rich.cells as rc
    import textual.strip as ts
    dancer = "\U0001F57A"
    t = gm.WidthTable()
    t.set(dancer, 1)            # claim the wide dancer is really 1 cell
    before_rich = rc.cell_len(dancer)
    before_ts = ts.cell_len(dancer)
    try:
        assert gm.install_width_overrides(t, force=True) is True
        assert rc.cell_len(dancer) == 1
        # Textual's directly-bound cell_len is repointed too, else layout still breaks.
        assert ts.cell_len(dancer) == 1
        # untouched glyphs keep rich's default
        assert rc.cell_len("A") == 1
    finally:
        assert gm.uninstall_width_overrides() is True
    assert rc.cell_len(dancer) == before_rich
    assert ts.cell_len(dancer) == before_ts

