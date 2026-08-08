#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Remove widget declarations
content = content.replace('        self._events_log: RichLog | None = None\n', '')
content = content.replace('        self._memory_log: RichLog | None = None    # v0.2.25.0\n', '')
content = content.replace('        self._inbox_log: RichLog | None = None      # v0.2.37.0\n', '')
content = content.replace('        self._atelier_log: RichLog | None = None  # atelier-d\n', '')

# Remove widget queries
content = content.replace('        self._events_log = self.query_one("#events-log", RichLog)\n', '')
content = content.replace('        self._memory_log = self.query_one("#memory-log", RichLog)\n', '')
content = content.replace('        self._inbox_log = self.query_one("#inbox-log", RichLog)\n', '')
content = content.replace('        self._atelier_log = self.query_one("#atelier-log", RichLog)  # atelier-d\n', '')

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
    f.write(content)
print("Successfully cleaned up widget declarations")