#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

old = '''    /* ── ARCHIVED: old vertical pane system (replaced by unified chat) ── */
    /* The side-pane, memory-pane, inbox-pane, live-pane, atelier-pane,
       tool-output-pane, and data-pane have been merged into the chat log.
       This CSS is kept for reference only. */
    .side-pane,
    #side-pane-scroll,
    #memory-pane,
    #inbox-pane,
    #live-pane,
    #atelier-pane,
    #tool-output-pane,
    #data-pane {
        display: none;
    }

    /* ── Unified chat layout: chat takes full width (100%) ────────────── */
    /* The main container is Horizontal (#main). Chat pane gets full width.
       All events, work, memory, inbox, tool output, and data science
       are merged into the chat log for full transparency. */
    #main {
        layout: horizontal;
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
    }'''

new = '''    /* ── Unified chat layout: chat takes full width (100%) ────────────── */
    /* The main container is Horizontal (#main). Chat pane gets full width.
       All events, work, memory, inbox, tool output, and data science
       are merged into the chat log for full transparency. */
    #main {
        layout: horizontal;
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
    }'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
        f.write(content)
    print("Successfully cleaned up CSS")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:200]))