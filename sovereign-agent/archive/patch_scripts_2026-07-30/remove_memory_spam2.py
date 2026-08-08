#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

old = '''    async def _refresh_memory_pane_worker(self) -> None:  # anti-lag-d
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.memory_garden import survey_memory
            health = await asyncio.to_thread(survey_memory, SETTINGS.paths.data_dir)
            
            # Update the memory metrics header in the chat
            self._update_memory_metrics_header(health)
            
            # Also write a periodic summary to the chat log
            if self._chat_log is not None:
                self._chat_log.write(
                    f"[dim]── memory snapshot ──[/dim]"
                )
                self._chat_log.write(
                    f"[bold]◊ {health.total_memories} memories[/bold]  "
                    f"[yellow]✦ {health.patterns_valuable} patterns[/yellow]  "
                    f"[cyan]◊ {health.atoms_active} atoms[/cyan]  "
                    f"[red]♥ {health.honor_notes} honor[/red]"
                )
                if health.patterns_active:
                    self._chat_log.write(
                        f"  [dim]active: {health.patterns_active}[/dim]"
                    )
                if health.hot_channels:
                    self._chat_log.write(
                        f"  [dim]hot: {', '.join(ch for ch, _ in health.hot_channels[:3])}[/dim]"
                    )
        except Exception as exc:  # noqa: BLE001
            self._chat_log.clear()
            self._chat_log.write(
                f"[dim](memory survey unavailable: {type(exc).__name__})[/dim]"
            )
            return

        self._chat_log.clear()

        # Section: total memories with the reorganization signal
        total = health.total_memories
        reorg_mark = ""
        if total >= 1000:
            reorg_mark = "  [yellow]◊ ready to tend[/yellow]"
        self._chat_log.write(
            f"[bold]◊ total: {total}[/bold]"
            f"{self._flash_suffix('total', total)}{reorg_mark}"
        )
        self._chat_log.write("")

        # Section: pattern self-perception (the most valuable signal)
        self._chat_log.write(
            "[bold cyan]patterns[/bold cyan]"
        )
        self._chat_log.write(
            f"  [yellow]✦[/yellow] valuable: {health.patterns_valuable}"
            f"{self._flash_suffix('patterns_valuable', health.patterns_valuable)}"
        )
        self._chat_log.write(
            f"  ● active:   {health.patterns_active}"
            f"{self._flash_suffix('patterns_active', health.patterns_active)}"
        )
        if health.patterns_dormant:
            self._chat_log.write(
                f"  [dim]○ dormant:  {health.patterns_dormant}[/dim]"
                f"{self._flash_suffix('patterns_dormant', health.patterns_dormant)}"
            )
        self._chat_log.write("")

        # Section: atoms (Aria's distilled knowledge about Kevin)
        self._chat_log.write(
            "[bold cyan]atoms[/bold cyan]"
        )
        self._chat_log.write(
            f"  ◊ active: {health.atoms_active}"
            f"{self._flash_suffix('atoms_active', health.atoms_active)}"
        )
        if health.atoms_total > health.atoms_active:
            superseded = health.atoms_total - health.atoms_active
            self._chat_log.write(
                f"  [dim]⊘ superseded: {superseded}[/dim]"
            )
        self._chat_log.write("")

        # Section: honor + field notes (cross-cutting witness threads)
        self._chat_log.write(
            "[bold cyan]witness[/bold cyan]"
        )
        self._chat_log.write(
            f"  [red]♥[/red] honor:       {health.honor_notes}"
            f"{self._flash_suffix('honor_notes', health.honor_notes)}"
        )
        self._chat_log.write(
            f"  ·  field-notes: {health.field_notes}"
            f"{self._flash_suffix('field_notes', health.field_notes)}"
        )
        self._chat_log.write("")

        # Section: substrate
        self._chat_log.write(
            "[bold cyan]substrate[/bold cyan]"
        )
        self._chat_log.write(
            f"  → interpretations: {health.provenance_entries}"
            f"{self._flash_suffix('provenance_entries', health.provenance_entries)}"
        )
        if health.corrections:
            self._chat_log.write(
                f"  ✎ corrections:     {health.corrections}"
            )
        self._chat_log.write("")

        # Section: hot channels (where things accumulate)
        if health.hot_channels:
            self._chat_log.write(
                "[bold cyan]hot channels[/bold cyan]"
            )
            for ch, count in health.hot_channels[:5]:
                self._chat_log.write(
                    f"  [dim]{count:3d}[/dim]  {ch}"
                )
            self._chat_log.write("")

        # Section: where things live (so Kevin and Aria both know)
        try:
            data_dir = SETTINGS.paths.data_dir
            self._chat_log.write(
                "[bold cyan]storage[/bold cyan]"
            )
            self._chat_log.write(
                f"  [dim]{data_dir}[/dim]"
            )
        except Exception:  # noqa: BLE001
            pass'''

new = '''    async def _refresh_memory_pane_worker(self) -> None:  # anti-lag-d
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.memory_garden import survey_memory
            health = await asyncio.to_thread(survey_memory, SETTINGS.paths.data_dir)
            
            # Update the memory metrics header only - no chat spam
            self._update_memory_metrics_header(health)
        except Exception:  # noqa: BLE001
            # Silently fail - don't spam chat with errors
            pass'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
        f.write(content)
    print("Successfully removed memory spam from chat")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:200]))