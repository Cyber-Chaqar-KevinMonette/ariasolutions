#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Replace all remaining _memory_log references with _chat_log
content = content.replace('self._memory_log', 'self._chat_log')

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
    f.write(content)
print("Replaced all _memory_log with _chat_log")