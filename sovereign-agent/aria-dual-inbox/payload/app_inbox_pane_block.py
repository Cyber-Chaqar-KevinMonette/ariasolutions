    def _refresh_inbox_pane(self) -> None:  # dual-inbox-d
        """Update the inbox pane (the 4th window) with the collaboration
        inbox, split into two clearly labeled directions:

          '◊ N waiting on you'  — Aria -> Kevin (direction=to_human, the
                                   original meaning of every request ever
                                   filed, unchanged in substance).
          '→ Aria'              — Kevin -> Aria (direction=to_aria, new):
                                   notes left via `sov requests tell` that
                                   she reads at her own safe checkpoints.

        Open items (most urgent first) carry their why/when/tags. Anything
        scheduled whose time has come surfaces under '⏰ due to revisit'. A
        'recent' section shows closed history with status markers, so
        scrolling up shows the whole story. Read-only; degrades silently.
        """
        if self._inbox_log is None:
            return
        try:
            from rich.markup import escape

            from sovereign_agent.config import SETTINGS
            from sovereign_agent.persistence.store import ErebloStore
            from sovereign_agent.workflow.requests import DIRECTION_TO_HUMAN, RequestStore
            rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
            open_items = rs.list_open(direction=DIRECTION_TO_HUMAN)
            due_items = rs.due()
            recent = rs.list(limit=40, direction=DIRECTION_TO_HUMAN)
            to_aria_items = rs.list_for_aria()
        except Exception as exc:  # noqa: BLE001
            self._inbox_log.clear()
            self._inbox_log.write(
                f"[dim](inbox unavailable: {type(exc).__name__})[/dim]")
            return

        self._inbox_log.clear()
        n_open = len(open_items)
        if n_open:
            self._inbox_log.write(f"[bold]◊ {n_open} waiting on you[/bold]")
        else:
            self._inbox_log.write("[dim]◊ inbox clear 📭[/dim]")
        self._inbox_log.write("")

        # Open requests — what needs attention now, with context.
        for r in open_items:
            pri = f"{r.priority_emoji} " if r.priority != "normal" else ""
            self._inbox_log.write(
                f"{r.emoji} {pri}[bold]{escape(r.title)}[/bold]  "
                f"[dim][{r.short_id}][/dim]")
            for line in r.context_lines():
                self._inbox_log.write(f"   [dim]{escape(line)}[/dim]")
        if open_items:
            self._inbox_log.write("")

        # Scheduled work whose time has come.
        if due_items:
            self._inbox_log.write("[bold yellow]⏰ due to revisit[/bold yellow]")
            for r in due_items:
                self._inbox_log.write(
                    f"  {r.status_emoji} {r.emoji} [dim]{escape(r.title)}[/dim]")
            self._inbox_log.write("")

        # → Aria — notes Kevin left FOR her, separate from her own asks.
        if to_aria_items:
            self._inbox_log.write(f"[bold magenta]→ Aria ({len(to_aria_items)})[/bold magenta]")
            for r in to_aria_items:
                pri = f"{r.priority_emoji} " if r.priority != "normal" else ""
                self._inbox_log.write(
                    f"  📮 {pri}[dim]{escape(r.title)}[/dim]  [dim][{r.short_id}][/dim]")
            self._inbox_log.write("")

        # Recent history with status markers (scroll up to see it all).
        closed = [r for r in recent if r.status not in ("open",)]
        if closed:
            self._inbox_log.write("[bold cyan]recent[/bold cyan]")
            for r in closed[:20]:
                self._inbox_log.write(
                    f"  {r.status_emoji} {r.emoji} [dim]{escape(r.title)}[/dim]")
