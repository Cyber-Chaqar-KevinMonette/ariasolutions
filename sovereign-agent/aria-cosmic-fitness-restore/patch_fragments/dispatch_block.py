        elif verb in ("cosmic", "fitness"):
            # /cosmic                → open the tester modal
            # /cosmic report         → print the fitness report inline
            # /cosmic mark <g> <v>   → record a glyph verdict
            # /cosmic verdicts       → list recorded verdicts
            sub = arg.split(maxsplit=1)
            head = sub[0].lower() if sub else ""
            tail = sub[1] if len(sub) > 1 else ""
            if head in ("", "open", "test"):
                self._show_cosmic_fitness()
            elif head in ("report", "check", "status"):
                self._cosmic_report_to_chat(include_scan=True)
            elif head in ("mark", "verdict"):
                self._cosmic_mark_glyph(tail)
            elif head in ("verdicts", "marks", "list"):
                self._cosmic_list_verdicts()
            elif head in ("probe", "measure", "widths"):
                self._cosmic_probe_widths()
            else:
                self._write_meta(
                    "[yellow]usage: /cosmic [report|probe|mark <glyph> "
                    "<good|replace|remove>|verdicts][/yellow]"
                )

        elif verb in ("workflows", "flows", "catalog", "wf"):
            # /workflows            -> open the catalog overlay
            # /workflows list       -> print the whole catalog inline
            sub = arg.split(maxsplit=1)
            head = sub[0].lower() if sub else ""
            if head in ("", "open", "menu", "show"):
                self._show_workflows()
            elif head in ("list", "text", "chat", "all", "dump"):
                try:
                    from ..workflow import catalog as _catalog
                    self._write_meta(_catalog.render_text(color=True))
                except Exception as exc:  # noqa: BLE001
                    self._write_meta(f"[red]catalog unavailable: {exc!r}[/red]")
            else:
                self._write_meta(
                    "[yellow]usage: /workflows [list][/yellow]  [dim](no arg opens the menu)[/dim]")
