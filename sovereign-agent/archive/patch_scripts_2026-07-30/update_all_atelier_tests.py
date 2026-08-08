#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'r') as f:
    content = f.read()

# Update all remaining atelier tests to use unified chat
content = content.replace('atelier = app.query_one("#chat-log", RichLog)', 'chat = app.query_one("#chat-log", RichLog)')
content = content.replace('atelier.lines', 'chat.lines')
content = content.replace('assert len(atelier.lines) > 0', 'assert len(chat.lines) > 0')

# Update test assertions to check chat instead of atelier
content = content.replace('assert len(atelier.lines) > lines_before_atelier', 'assert len(chat.lines) > lines_before')
content = content.replace('assert any("new.py" in str(line) for line in atelier.lines)', 'assert any("new.py" in str(line) for line in chat.lines)')
content = content.replace('assert len(events_log.lines) > 0', 'assert len(chat.lines) > 0')

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'w') as f:
    f.write(content)
print("Updated all atelier tests for unified chat")