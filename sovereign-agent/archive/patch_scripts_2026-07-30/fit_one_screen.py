#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Add CSS to prevent overflow and fit everything on one screen
old = '''    /* ── Unified chat layout: chat takes full width (100%) ────────────── */
    /* The main container is Horizontal (#main). Chat pane gets full width.
       All events, work, memory, inbox, tool output, and data science
       are merged into the chat log for full transparency. */
    #main {
        layout: horizontal;
        height: 100%;
        width: 100%;
    }
    #main #movie-pane {
        width: 1fr;
        min-width: 30;
    }
    .chat-pane {
        width: 1fr;
        min-width: 50;
        padding: 0 1;
        background: $surface;
        height: 100%;
    }
    #chat-log {
        width: 100%;
        min-width: 1;
        height: 1fr;
    }
    /* Memory metrics header styling */
    .memory-metrics-header {
        padding: 0 1;
        margin: 0 0 1 0;
        color: $accent;
        text-style: bold;
        height: 1;
    }
    /* Ensure chat pane and its children fill available space */
    .chat-pane > Vertical {
        height: 100%;
    }
    .chat-pane > RichLog {
        height: 1fr;
    }'''

new = '''    /* ── Unified chat layout: chat takes full width (100%) ────────────── */
    /* The main container is Horizontal (#main). Chat pane gets full width.
       All events, work, memory, inbox, tool output, and data science
       are merged into the chat log for full transparency. */
    #main {
        layout: horizontal;
        height: 100%;
        width: 100%;
        overflow: hidden;
    }
    #main #movie-pane {
        width: 1fr;
        min-width: 30;
    }
    .chat-pane {
        width: 1fr;
        min-width: 50;
        padding: 0 1;
        background: $surface;
        height: 100%;
        overflow: hidden;
    }
    #chat-log {
        width: 100%;
        min-width: 1;
        height: 1fr;
        max-height: 1fr;
    }
    /* Memory metrics header styling */
    .memory-metrics-header {
        padding: 0 1;
        margin: 0 0 1 0;
        color: $accent;
        text-style: bold;
        height: 1;
    }
    /* Ensure chat pane and its children fill available space */
    .chat-pane > Vertical {
        height: 100%;
    }
    .chat-pane > RichLog {
        height: 1fr;
    }
    /* Compact palette row - fit on one screen */
    #palette-row {
        height: 1;
        padding: 0 1;
    }
    #palette-row MenuTriggerButton {
        padding: 0 1;
        height: 1;
    }'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
        f.write(content)
    print("Successfully added CSS to prevent overflow and fit on one screen")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:200]))