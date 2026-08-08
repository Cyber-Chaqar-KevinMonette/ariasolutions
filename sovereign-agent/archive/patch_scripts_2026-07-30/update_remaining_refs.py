#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'r') as f:
    content = f.read()

# Replace all remaining atelier-log references with chat-log
content = content.replace('#atelier-log', '#chat-log')
content = content.replace('#events-log', '#chat-log')
content = content.replace('#memory-log', '#chat-log')
content = content.replace('#inbox-log', '#chat-log')

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'w') as f:
    f.write(content)
print("Updated all remaining old pane references")