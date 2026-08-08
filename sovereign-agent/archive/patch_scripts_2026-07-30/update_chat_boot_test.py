#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'r') as f:
    content = f.read()

# Update test_chat_pane_exists_and_is_empty_on_boot
old_test = '''@pytest.mark.asyncio
async def test_chat_pane_exists_and_is_empty_on_boot():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat = app.query_one("#chat-log", RichLog)
        assert chat is not None
        assert len(chat.lines) == 0'''

new_test = '''@pytest.mark.asyncio
async def test_chat_pane_exists_and_has_welcome_messages():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat = app.query_one("#chat-log", RichLog)
        assert chat is not None
        # Chat has welcome messages on boot, not empty
        assert len(chat.lines) > 0'''

content = content.replace(old_test, new_test)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'w') as f:
    f.write(content)
print("Updated test_chat_pane_exists_and_has_welcome_messages")