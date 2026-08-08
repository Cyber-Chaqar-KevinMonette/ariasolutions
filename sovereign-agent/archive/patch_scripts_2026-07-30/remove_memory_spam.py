#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Fix 1: Remove memory spam from chat - only update header, don't write to chat log
old = '''    @work(exclusive=True, group="memory-refresh")
    async def _refresh_memory_pane_worker(self) -> None:  # anti-lag-d
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
                f"[dim](memory survey unavailable: {type(exc).__name__})[/dim]")
            return

        self._chat_log.clear()'''

new = '''    @work(exclusive=True, group="memory-refresh")
    async def _refresh_memory_pane_worker(self) -> None:  # anti-lag-d
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.memory_garden import survey_memory
            health = await asyncio.to_thread(survey_memory, SETTINGS.paths.data_dir)
            
            # Update the memory metrics header in the chat
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