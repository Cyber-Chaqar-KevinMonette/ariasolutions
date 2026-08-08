#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

old = '''                yield RichLog(
                    id="chat-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True, max_lines=1000,
                    min_width=1,
                )
            # ── Archived panes (hidden but preserved for tests/compat) ──
            with Vertical(id="side-pane", classes="side-pane"):
                with VerticalScroll(id="side-pane-scroll"):
                    with Vertical(id="memory-pane"):
                        yield Label("◊ memory", classes="pane-title")
                        yield RichLog(
                            id="memory-log",
                            highlight=True, markup=True, wrap=True,
                            auto_scroll=False, max_lines=200,
                            min_width=1,
                        )
                    with Vertical(id="inbox-pane"):
                        yield Label("◊ inbox", classes="pane-title")
                        yield RichLog(
                            id="inbox-log",
                            highlight=True, markup=True, wrap=True,
                            auto_scroll=False, max_lines=300,
                            min_width=1,
                        )
                    with Vertical(id="live-pane"):
                        yield Label("◊ live", classes="pane-title")
                        yield RichLog(
                            id="events-log",
                            highlight=True, markup=True, wrap=True,
                            auto_scroll=True, max_lines=200,
                            min_width=1,
                        )
                    with Vertical(id="atelier-pane"):
                        yield Label("◊ atelier", classes="pane-title")
                        yield RichLog(
                            id="atelier-log",
                            highlight=True, markup=True, wrap=True,
                            auto_scroll=True, max_lines=300,
                            min_width=1,
                        )
                    with Vertical(id="tool-output-pane"):
                        yield Label("◊ tool output", classes="pane-title")
                        yield RichLog(
                            id="tool-output",
                            highlight=True, markup=True, wrap=True,
                            auto_scroll=True, max_lines=200,
                            min_width=1,
                        )
                    with Vertical(id="data-pane"):
                        yield Label("◊ data", classes="pane-title")
                        yield RichLog(
                            id="data-log",
                            highlight=True, markup=True, wrap=True,
                            auto_scroll=False, max_lines=200,
                            min_width=1,
                        )
        # chat-box-above-buttons-d (Kevin, 2026-07-26): "put the chat box'''

new = '''                yield RichLog(
                    id="chat-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True, max_lines=1000,
                    min_width=1,
                )
        # chat-box-above-buttons-d (Kevin, 2026-07-26): "put the chat box'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
        f.write(content)
    print("Successfully removed archived panes from DOM")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:200]))