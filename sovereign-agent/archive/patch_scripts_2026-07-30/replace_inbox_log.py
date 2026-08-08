#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Replace inbox_log with chat_log
content = content.replace('self._inbox_log', 'self._chat_log')

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
    f.write(content)
print("Successfully replaced inbox_log with chat_log")