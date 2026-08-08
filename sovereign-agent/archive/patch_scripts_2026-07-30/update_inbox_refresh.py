#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Replace the inbox refresh worker to not clear chat
old = '''    @work(exclusive=True, group="inbox-refresh")
    async def _refresh_inbox_pane_worker(self) -> None:  # anti-lag-d
        from rich.markup import escape

        try:
            open_items, due_items, recent, to_aria_items = await asyncio.to_thread(
                self._read_inbox_data
            )
        except Exception as exc:  # noqa: BLE001
            self._chat_log.clear()
            self._chat_log.write(
                f"[dim](inbox unavailable: {type(exc).__name__})[/dim]")
            return

        self._chat_log.clear()'''

new = '''    @work(exclusive=True, group="inbox-refresh")
    async def _refresh_inbox_pane_worker(self) -> None:  # anti-lag-d
        from rich.markup import escape

        try:
            open_items, due_items, recent, to_aria_items = await asyncio.to_thread(
                self._read_inbox_data
            )
        except Exception as exc:  # noqa: BLE001
            self._chat_log.write(
                f"[dim](inbox unavailable: {type(exc).__name__})[/dim]")
            return

        # Don't clear chat - just write inbox content'''

content = content.replace(old, new)

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
    f.write(content)
print("Updated _refresh_inbox_pane_worker to not clear chat")