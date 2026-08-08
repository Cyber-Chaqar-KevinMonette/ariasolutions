class WorkflowsScreen(ModalScreen):
    """▸ flows — the live workflows catalog.

    A scrollable, always-current guide to every workflow she can do and
    exactly how to drive each one with her. The content is rendered straight
    from workflow/catalog.py (the single source of truth), so it can never
    drift from what she actually does. Esc / q / Close to dismiss.
    """

    BINDINGS = [Binding("escape,q", "close_workflows", "close")]

    def action_close_workflows(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        # Bulletproof exit: Esc or q always closes, every other key falls
        # through so the catalog can still scroll.
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        # The Close button — the no-keyboard-needed escape hatch.
        event.stop()
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        # Render from the catalog. Defensive: never let a content error
        # leave the operator stuck on a blank modal.
        try:
            from ..workflow import catalog as _catalog
            body = _catalog.render_text(color=True)
        except Exception as exc:  # noqa: BLE001
            body = f"[red]workflows catalog unavailable: {exc!r}[/red]"
        with Vertical(id="workflows-modal"):
            with VerticalScroll(id="workflows-scroll"):
                yield Static(body, id="workflows-content")
            yield Button("✕  Close   (Esc / q)", id="workflows-close",
                         variant="primary")

    DEFAULT_CSS = """
    WorkflowsScreen {
        align: center middle;
        background: $surface 60%;
    }
    #workflows-modal {
        width: 86;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #workflows-scroll {
        height: auto;
        max-height: 80%;
    }
    #workflows-close {
        margin: 1 0 0 0;
        width: 100%;
    }
    """


# ─── Cosmic Fitness (v0.2.41) ───────────────────────────────────────────────
#
# The visual-systems gym. Two surfaces share one source of truth
# (cockpit/cosmic_fitness.py):
#
#   • GlyphButton          a tappable glyph; clicking drops it in the input.
#   • CosmicFitnessScreen  the F-tester modal: a fitness verdict, the live
#                          special-effects showcase, and the full glyph
#                          inventory (every glyph colour-coded by width-
#                          safety, click-to-insert). Opened by the
#                          "◊ cosmic" reference button or /cosmic.
#   • the inline picker    a compact, always-near-the-input strip toggled by
#                          Ctrl-G or /pick (built in CockpitApp.compose).
#
# Width discipline is honoured throughout: glyphs render in their own button
# cells / flowing text, never inside a width-counted box layout, so showing
# even the wide colour emoji here can't corrupt anything.




class GlyphButton(Button):
    """A clickable glyph. Carries its GlyphSpec; clicking inserts the char.

    The label is normally the glyph itself. A status-coloured CSS class gives
    an at-a-glance read of width-safety; the tooltip carries the full detail.

    ``safe_display``: when True (used in the width-counted inventory grid), a
    glyph that is NOT layout-safe (emoji/wide/composite) is shown as its small
    status BADGE rather than the raw glyph. This is the cockpit's own law
    applied to the tester: rendering a width-unstable glyph inside a counted
    grid is exactly what nudges borders on a terminal that draws it wider than
    Textual's model expects. The real glyph still rides in the tooltip and is
    what gets inserted on click — so it stays one tap from your message, where
    flowing text handles it fine.

    ``in_modal`` distinguishes the two homes so DOM ids stay unique.
    """

    def __init__(self, spec, *, in_modal: bool = False,
                 safe_display: bool = False) -> None:
        self.spec = spec
        self.in_modal = in_modal
        layout_safe = spec.status in ("safe", "convention")
        self._badge_mode = bool(safe_display and not layout_safe)
        # Derive a DOM-safe, unique id from the codepoint(s).
        token = spec.codepoint.replace("U+", "").replace(" ", "_").lower()
        prefix = "mg" if in_modal else "pg"
        # In badge mode show the class badge (a safe glyph); else the real one.
        badge = "?"
        if _cf is not None:
            badge = _cf.STATUS_BADGE.get(spec.status, "?")
        label = badge if self._badge_mode else spec.char
        super().__init__(label, id=f"{prefix}-{token}")
        self.add_class("glyph-btn")
        self.add_class(f"gstatus-{spec.status}")
        if self._badge_mode:
            self.add_class("glyph-badged")
        blurb = ""
        if _cf is not None:
            blurb = _cf.STATUS_BLURB.get(spec.status, "")
        alt = (f"\nsafe variant: {spec.safe_alternative}"
               if getattr(spec, "safe_alternative", None) else "")
        shown = (f"\n[shown as {badge} — width-unstable, see above]"
                 if self._badge_mode else "")
        self.tooltip = (
            f"{spec.char}  {spec.label}\n"
            f"{spec.codepoint} · {spec.unicode_name}\n"
            f"{spec.status} — {blurb}{alt}{shown}\n"
            f"(click to insert the real glyph)"
        )


class CosmicFitnessScreen(ModalScreen):
    """The Cosmic Fitness tester + special-effects showcase + glyph picker."""

    BINDINGS = [Binding("escape,q", "close_cosmic", "close")]

    def action_close_cosmic(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        # Bulletproof exit (mirrors HelpScreen): Esc / q always closes.
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        event.stop()
        button = event.button
        if isinstance(button, GlyphButton):
            # Insert into the input and close so the operator immediately
            # sees it land. The inline picker (Ctrl-G) is the stay-open one.
            try:
                self.app._insert_glyph(button.spec.char)
            except Exception:  # noqa: BLE001
                pass
            self.app.pop_screen()
            return
        # Any other button in here is the Close button.
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="cosmic-modal"):
            with VerticalScroll(id="cosmic-scroll"):
                yield Static(
                    "[b]\u25ca Cosmic Fitness[/b]  "
                    "[dim]Aria's visual-systems gym[/dim]",
                    id="cosmic-title",
                )

                # ── Fitness verdict ───────────────────────────────────────
                if _cf is not None:
                    try:
                        report = _cf.run_cosmic_fitness(include_scan=True)
                        for line in report.render_lines():
                            yield Static(line, classes="cosmic-report-line")
                    except Exception as exc:  # noqa: BLE001
                        yield Static(
                            f"[yellow]fitness report unavailable: {exc!r}[/yellow]"
                        )
                else:
                    yield Static(
                        "[yellow]cosmic_fitness module unavailable — "
                        "showing nothing dynamic.[/yellow]"
                    )

                # ── Width legend ──────────────────────────────────────────
                yield Static(
                    "\n[b]how to read the colours[/b]\n"
                    "  [green]\u2713 safe[/green]        one cell everywhere — use anywhere\n"
                    "  [cyan]\u25ca convention[/cyan]  ambiguous but blessed-narrow — safe in practice\n"
                    "  [magenta]\u25c9 emoji[/magenta]       narrow by spec, 2 cells in most terminals — sandbox only\n"
                    "  [yellow]\u25b8 wide[/yellow]        two cells — lovely in chat, never in a layout glyph\n"
                    "  [red]\u2717 composite[/red]   multi-codepoint — terminal-dependent, avoid in the TUI",
                    classes="cosmic-legend",
                )

                # ── Special effects showcase ──────────────────────────────
                yield Static(
                    "\n[b]\u2726 god-tier special effects[/b]   "
                    "[dim]live — these are real, running right now[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_effects()

                # ── Glyph animations showcase (v0.2.42) ───────────────────
                yield Static(
                    "\n[b]\u25c9 animated glyphs[/b]   "
                    "[dim]frame-cycling — also live[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_animations()

                # ── Animated special effects showcase (v0.2.42) ───────────
                yield Static(
                    "\n[b]\u2726 animated special effects[/b]   "
                    "[dim]frames + glow/colour — the beating heart lives here[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_animated_effects()

                # ── The sandbox (GlyphStage) demo ─────────────────────────
                yield Static(
                    "\n[b]\u25a3 the GlyphStage[/b]   "
                    "[dim]a bounded container for living glyphs — holding "
                    "width-stable ones here so the border stays put[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_sandbox_demo()

                # ── Glyph inventory ───────────────────────────────────────
                yield Static(
                    "\n[b]\u25ca glyph inventory[/b]   "
                    "[dim]tap any glyph to drop the real character into your "
                    "message[/dim]\n"
                    "[dim]width-unstable glyphs (emoji/wide/composite) show "
                    "their class badge here — drawing them raw in this grid is "
                    "what nudges borders. The real glyph still inserts on tap, "
                    "and you can watch them live in the sandbox above.[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_inventory()

            yield Button("\u2715  Close   (Esc / q)", id="cosmic-close",
                         variant="primary")

    # ── compose helpers ──────────────────────────────────────────────────

    def _compose_effects(self):
        """Yield a labelled, live row per special effect (guarded)."""
        if _cf is None:
            return
        try:
            from .breathing_glyph import BreathingBorder
        except Exception:  # noqa: BLE001 — Textual missing somehow
            BreathingBorder = None  # type: ignore
        for fx in _cf.special_effects():
            with Horizontal(classes="fx-row"):
                made = False
                if BreathingBorder is not None:
                    try:
                        length = fx.length if fx.kind == "ripple" else 10
                        step = fx.phase_step if fx.kind == "ripple" else 0.0
                        widget = BreathingBorder(
                            length=length,
                            glyph=fx.glyph,
                            config=fx.config,
                            base_hex=fx.base_hex,
                            bg_hex="#101018",
                            phase_step=step,
                            assume_width_safe=True,
                        )
                        widget.add_class("fx-live")
                        yield widget
                        made = True
                    except Exception:  # noqa: BLE001 — degrade to static
                        made = False
                if not made:
                    yield Static(fx.glyph * 10, classes="fx-live")
                yield Static(
                    f"[b]{fx.name}[/b] · [dim]{fx.tagline}[/dim]  "
                    f"[dim]\\[{fx.label}][/dim]\n{fx.description}",
                    classes="fx-desc",
                )

    def _compose_inventory(self):
        """Yield each category title + a grid of clickable GlyphButtons."""
        if _cf is None:
            return
        try:
            cats = _cf.curated_categories()
        except Exception:  # noqa: BLE001
            return
        for cat in cats:
            stable = sum(1 for s in cat.glyphs if s.status in ("safe", "convention"))
            unstable = len(cat.glyphs) - stable
            note = (f"  [dim]({stable} stable"
                    + (f", {unstable} badged" if unstable else "")
                    + ")[/dim]")
            yield Static(
                f"\n[b]{cat.name}[/b]  [dim]{cat.blurb}[/dim]{note}",
                classes="cat-title",
            )
            with Grid(classes="glyph-grid"):
                for spec in cat.glyphs:
                    yield GlyphButton(spec, in_modal=True, safe_display=True)

    def _compose_animations(self):
        """Yield a labelled live row per layout-safe animation."""
        if _cf is None:
            return
        try:
            from .animated_glyph import AnimatedGlyph
        except Exception:  # noqa: BLE001
            AnimatedGlyph = None  # type: ignore
        for an in _cf.animations():
            if not an.is_layout_safe:
                continue  # sandbox-only ones go in the GlyphStage demo below
            with Horizontal(classes="fx-row"):
                made = False
                if an.is_universal and AnimatedGlyph is not None:
                    try:
                        w = AnimatedGlyph(an)
                        w.add_class("anim-live")
                        yield w
                        made = True
                    except Exception:  # noqa: BLE001 — degrade to static
                        made = False
                if not made:
                    yield Static("\u25cc", classes="anim-live glyph-badged")
                tail = "" if an.is_universal else \
                    "  [dim](listed — ambiguous width)[/dim]"
                yield Static(
                    f"[b]{an.name}[/b] · [dim]{an.tagline}[/dim]  "
                    f"[dim]\\[{an.label}][/dim]{tail}\n{an.description}",
                    classes="fx-desc",
                )

    def _compose_animated_effects(self):
        """Yield a labelled live row per layout-safe animated effect."""
        if _cf is None:
            return
        try:
            from .animated_glyph import AnimatedEffect
        except Exception:  # noqa: BLE001
            AnimatedEffect = None  # type: ignore
        for ae in _cf.animated_effects():
            if not ae.is_layout_safe:
                continue  # sandbox-only (moon glow) shown in the stage demo
            with Horizontal(classes="fx-row"):
                made = False
                if ae.is_universal and AnimatedEffect is not None:
                    try:
                        w = AnimatedEffect(ae)
                        w.add_class("anim-live")
                        yield w
                        made = True
                    except Exception:  # noqa: BLE001
                        made = False
                if not made:
                    yield Static("\u25cc", classes="anim-live glyph-badged")
                tail = "" if ae.is_universal else \
                    "  [dim](listed — ambiguous width)[/dim]"
                yield Static(
                    f"[b]{ae.name}[/b] · [dim]{ae.tagline}[/dim]  "
                    f"[dim]\\[{ae.label}][/dim]{tail}\n{ae.description}",
                    classes="fx-desc",
                )

    def _compose_sandbox_demo(self):
        """Demonstrate the GlyphStage with width-STABLE living glyphs.

        Hard-won lesson (v0.2.44): a bounded container fully isolates the layout
        *outside* it, but it cannot perfectly contain a font-variable emoji's
        width on its own bordered line — when a terminal draws an emoji narrower
        (or wider) than Textual's model, that deficit propagates to the line's
        border no matter how much slack there is. So we never render font-
        variable emoji on a bordered, width-counted line. The stage here holds
        layout-safe animations (rock-steady on every terminal); the dancer and
        the moon live in your chat, where flowing text renders them free.
        """
        if _cf is None:
            return
        try:
            from .animated_glyph import AnimatedEffect, AnimatedGlyph
            from .glyph_stage import GlyphStage
        except Exception:  # noqa: BLE001
            GlyphStage = None  # type: ignore
            AnimatedGlyph = None  # type: ignore
            AnimatedEffect = None  # type: ignore

        if GlyphStage is None:
            yield Static("[dim](sandbox unavailable in this build)[/dim]")
            return

        # The stage holds only universal one-cell living glyphs — a braille
        # spinner, a block-shaded pulse, an aurora swatch — which render
        # identically on every terminal, so the border is rock-steady.
        try:
            # v0.2.46 — ripple_aurora=True: the stage's border is the Aurora
            # ripple — a full spectrum wrapped around it, rotating over time,
            # with the glow rippling on top. The aurora glyph's hue-cycle, made
            # into a frame, around the swatch that inspired it.
            stage = GlyphStage(cells=26, title="GlyphStage", ripple_aurora=True)
            with stage, Vertical(classes="sandbox-col"):
                if AnimatedGlyph is not None:
                    spinner = _cf.animation_by_key("spinner")
                    ring = _cf.animation_by_key("ring")
                    if spinner is not None:
                        with Horizontal(classes="sandbox-line"):
                            yield Static("spinner    ", classes="sandbox-cap")
                            yield AnimatedGlyph(spinner)
                    if ring is not None:
                        with Horizontal(classes="sandbox-line"):
                            yield Static("pulse      ", classes="sandbox-cap")
                            yield AnimatedGlyph(ring)
                if AnimatedEffect is not None:
                    aurora = _cf.animated_effect_by_key("aurora")
                    if aurora is not None:
                        with Horizontal(classes="sandbox-line"):
                            yield Static("aurora     ", classes="sandbox-cap")
                            yield AnimatedEffect(aurora)
                    # NB: the Aurora Heart (♥, hue-cycling) is a registered
                    # effect but is intentionally NOT rendered live here. ♥ is
                    # convention-tier (one cell in practice) but NOT *universal*
                    # — it's EAW-ambiguous — and every glyph animated live in
                    # this bordered modal must be universal so no terminal can
                    # shift a border (the v0.2.45 width law / modal test). It
                    # renders free in chat instead, like the moon and dancer.
        except Exception as exc:  # noqa: BLE001
            yield Static(f"[yellow]sandbox demo unavailable: {exc!r}[/yellow]")
            return
        yield Static(
            "[dim]↑ a GlyphStage holding width-stable living glyphs — the "
            "border never moves. Wide emoji and the dancer go in a stage too, "
            "but a counted, bordered line can't perfectly hold a glyph your "
            "terminal sizes unpredictably — so to see those, tap one in the "
            "inventory and watch it land in your message, where it renders "
            "free.[/dim]",
            classes="sandbox-note",
        )

    DEFAULT_CSS = """
    CosmicFitnessScreen {
        align: center middle;
        background: $surface 60%;
    }
    #cosmic-modal {
        width: 84;
        height: auto;
        max-height: 92%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #cosmic-scroll {
        height: auto;
        max-height: 84%;
    }
    #cosmic-title {
        text-align: center;
        margin: 0 0 1 0;
    }
    .cosmic-report-line { height: auto; }
    .cosmic-legend {
        margin: 1 0 0 0;
        padding: 1 1;
        background: $panel;
        border: round $secondary;
    }
    .cosmic-section {
        margin: 1 0 0 0;
        color: $accent;
    }
    .cat-title { height: auto; }
    .fx-row {
        height: auto;
        margin: 0 0 1 0;
    }
    .fx-live {
        width: 20;
        content-align: left middle;
        padding: 0 1 0 0;
    }
    .fx-desc { width: 1fr; height: auto; }
    .anim-live {
        width: 4;
        content-align: left middle;
        color: $accent;
        padding: 0 1 0 0;
    }
    .sandbox-col { height: auto; }
    .sandbox-line { height: auto; }
    .sandbox-emoji { width: auto; height: 1; padding: 0 0 0 0; }
    .sandbox-cap { width: auto; height: 1; color: $text-muted; }
    .sandbox-note { height: auto; margin: 0 0 1 0; }
    #cosmic-modal .glyph-badged { text-style: dim; }
    .glyph-grid {
        grid-size: 5;
        grid-gutter: 0 1;
        grid-rows: 3;
        height: auto;
        margin: 0 0 1 0;
    }
    #cosmic-modal .glyph-btn {
        width: 1fr;
        min-width: 6;
        height: 3;
        border: round $primary 40%;
    }
    #cosmic-modal .glyph-btn:hover { border: round $accent; }
    #cosmic-close {
        margin: 1 0 0 0;
        width: 100%;
    }
    """


# ─── Command palette (v0.2.31.0) ────────────────────────────────────────────
#
# A row of clickable buttons that paste common `sov` commands into the input
# box (without sending). The operator can review/edit before pressing Enter.
# Designed for speed without sacrificing review — Kevin's exact ask.
#
# Visual states:
#   • idle      — default, accent border
#   • flash     — brief green pulse after a click (operator feedback)
#   • running   — cyan glow while Aria is executing this command (so the
#                 operator can see at a glance what's currently active)
#
# Only read-only / reversible commands appear on the palette. Destructive
# operations (halt, backup restore, migrations) deliberately don't get a
# button — those should go through Aria's conversation pipeline where the
# Tier-3 confirm gate lives.
