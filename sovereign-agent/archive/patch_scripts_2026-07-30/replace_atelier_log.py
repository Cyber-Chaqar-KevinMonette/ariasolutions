#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Replace atelier_log with chat_log
content = content.replace('self._atelier_log', 'self._chat_log')

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
    f.write(content)
print("Successfully replaced atelier_log with chat_log")