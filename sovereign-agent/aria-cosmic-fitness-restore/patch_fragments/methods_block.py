    # ----------------------------------------------------------------- #
    #  ▸ flows  —  the workflows catalog (what she can do + how)        #
    # ----------------------------------------------------------------- #
    def _show_workflows(self) -> None:
        """Toggle the workflows catalog overlay (▸ flows / /workflows)."""
        if isinstance(self.screen, WorkflowsScreen):
            self.pop_screen()
        else:
            self.push_screen(WorkflowsScreen())

    def _insert_glyph(self, char: str) -> None:
        """Insert a glyph at the input cursor and refocus the input."""
        try:
            input_box = self.query_one("#input-box", Input)
        except Exception:  # noqa: BLE001
            return
        try:
            input_box.insert_text_at_cursor(char)
        except Exception:  # noqa: BLE001 — very old Textual; append instead
            input_box.value = (input_box.value or "") + char
        input_box.focus()

    def _show_cosmic_fitness(self) -> None:
        """Open the Cosmic Fitness tester modal. Button, /cosmic, /fitness."""
        if _cf is not None and not _cf.cosmic_fitness_enabled():
            self._write_meta(
                "[dim]Cosmic Fitness disabled (SOV_NO_COSMIC_FITNESS set)[/dim]"
            )
            return
        try:
            self.push_screen(CosmicFitnessScreen())
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not open Cosmic Fitness: {exc!r}[/red]")

    def _cosmic_report_to_chat(self, include_scan: bool = True) -> None:
        """Print the Cosmic Fitness report inline (for /cosmic report)."""
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        try:
            report = _cf.run_cosmic_fitness(include_scan=include_scan)
            for line in report.render_lines():
                self._write_meta(line)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]fitness report failed: {exc!r}[/red]")

    def _cosmic_mark_glyph(self, arg: str) -> None:
        """Record an operator verdict on a glyph. /cosmic mark <glyph> <verdict> [note]."""
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        parts = arg.split(maxsplit=2)
        if len(parts) < 2:
            self._write_meta(
                "[yellow]usage: /cosmic mark <glyph> good|replace|remove [note][/yellow]"
            )
            return
        glyph, verdict = parts[0], parts[1].lower()
        note = parts[2] if len(parts) > 2 else ""
        if verdict not in ("good", "replace", "remove"):
            self._write_meta(
                "[yellow]verdict must be: good | replace | remove[/yellow]"
            )
            return
        try:
            from ..config import SETTINGS
            store = _cf.GlyphVerdictStore(SETTINGS.paths.data_dir)
            rec = store.record(glyph, verdict, note)
            alt = rec.get("suggested_alternative")
            alt_s = f"  (safe variant: {alt})" if alt and verdict == "replace" else ""
            self._write_meta(
                f"[green]\u2713 marked[/green] {glyph} [{rec['codepoint']}] "
                f"as [b]{verdict}[/b]{alt_s}"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not record verdict: {exc!r}[/red]")

    def _cosmic_list_verdicts(self) -> None:
        """List recorded glyph verdicts. /cosmic verdicts."""
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        try:
            from ..config import SETTINGS
            store = _cf.GlyphVerdictStore(SETTINGS.paths.data_dir)
            for line in store.render_lines():
                self._write_meta(line)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not list verdicts: {exc!r}[/red]")

    def _cosmic_probe_widths(self) -> None:
        """Measure THIS terminal's real glyph widths and report disagreements.

        Tier 1 of the accounting system: suspends the TUI, runs a DSR cursor
        probe on the ambiguous/wide glyphs we ship, and reports which ones the
        terminal actually draws at 2 cells versus what rich assumes. Patches no
        rendering — purely informational, so it cannot break anything.
        """
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        try:
            from . import glyph_metrics as gm
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]glyph_metrics unavailable: {exc!r}[/red]")
            return
        if not gm.metrics_enabled():
            self._write_meta(
                f"[yellow]width probe disabled ({gm.METRICS_KILL_ENV} set)[/yellow]"
            )
            return

        # Glyphs worth measuring: a few universal anchors (which MUST come back
        # as 1 cell), plus every ambiguous/wide glyph we actually ship.
        suspects: list[str] = []
        seen: set[str] = set()

        def _add(g: str) -> None:
            if g and g not in seen:
                seen.add(g)
                suspects.append(g)

        for anchor in ("A", "\u2588", "\u28FF"):
            _add(anchor)
        for cat in _cf.curated_categories():
            for spec in cat.glyphs:
                if not _cf.is_universal_width(spec.char):
                    _add(spec.char)
        for an in _cf.animations():
            for f in an.frames:
                if not _cf.is_universal_width(f):
                    _add(f)
        for ae in _cf.animated_effects():
            for f in ae.frames:
                if not _cf.is_universal_width(f):
                    _add(f)
        for eff in _cf.special_effects():
            if not _cf.is_universal_width(eff.glyph):
                _add(eff.glyph)

        self._write_meta(f"[dim]probing {len(suspects)} glyphs on this terminal…[/dim]")
        table = gm.WidthTable()
        try:
            with self.suspend():
                table = gm.probe_terminal_widths(suspects)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]probe failed: {exc!r}[/red]")
            return

        if not table:
            self._write_meta(
                "[yellow]measured nothing — this terminal didn't answer the "
                "cursor-position query (or isn't a real TTY). Curation stays "
                "in effect; nothing changed.[/yellow]"
            )
            return

        try:
            from rich.cells import cell_len
        except Exception:  # noqa: BLE001
            def cell_len(s: str) -> int:  # type: ignore
                return 1
        overwide = gm.overwide_glyphs(table)
        disagreements = []
        for g in suspects:
            w = table.get(g)
            if w is None:
                continue
            assumed = cell_len(g)
            if w != assumed:
                disagreements.append((g, assumed, w))

        self._write_meta(
            f"[b]width probe[/b] — {len(table)} measured, "
            f"{len(overwide)} draw wide, {len(disagreements)} disagree with rich:"
        )
        if disagreements:
            for g, assumed, w in disagreements:
                self._write_meta(
                    f"  [yellow]U+{ord(g[0]):04X}[/yellow] {g}  "
                    f"rich={assumed} → terminal=[b]{w}[/b]"
                )
        else:
            self._write_meta(
                "  [green]no disagreements — rich's widths already match your "
                "terminal for every glyph we ship.[/green]"
            )
        self._write_meta(
            "[dim]Measured on YOUR terminal, now. The disagreements are why "
            "borders shift; they're already kept out of counted layouts.[/dim]"
        )

