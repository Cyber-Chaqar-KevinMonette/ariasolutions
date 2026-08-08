#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'r') as f:
    content = f.read()

# Update test_atelier_pane_exists_and_is_empty_on_boot
old_test1 = '''@pytest.mark.asyncio
async def test_atelier_pane_exists_and_is_empty_on_boot():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)
        assert atelier is not None
        assert len(atelier.lines) == 0'''

new_test1 = '''@pytest.mark.asyncio
async def test_chat_pane_exists_and_is_empty_on_boot():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat = app.query_one("#chat-log", RichLog)
        assert chat is not None
        assert len(chat.lines) == 0'''

content = content.replace(old_test1, new_test1)

# Update test_render_event_routes_work_write_to_atelier_pane_and_chat
old_test2 = '''@pytest.mark.asyncio
async def test_render_event_routes_work_write_to_atelier_pane_and_chat():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat_log = app.query_one("#chat-log", RichLog)
        atelier = app.query_one("#atelier-log", RichLog)
        
        lines_before_chat = len(chat_log.lines)
        lines_before_atelier = len(atelier.lines)

        raw = json.dumps({
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-write",
            "payload": {"op": "write", "path": "/tmp/new.py", "added": 3, "diff_excerpt": "hi"},
        })
        app._render_event(raw)
        await pilot.pause()

        assert len(atelier.lines) > lines_before_atelier
        assert any("new.py" in str(line) for line in atelier.lines)
        assert len(chat_log.lines) > lines_before_chat'''

new_test2 = '''@pytest.mark.asyncio
async def test_render_event_routes_work_write_to_chat():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat_log = app.query_one("#chat-log", RichLog)
        
        lines_before = len(chat_log.lines)

        raw = json.dumps({
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-write",
            "payload": {"op": "write", "path": "/tmp/new.py", "added": 3, "diff_excerpt": "hi"},
        })
        app._render_event(raw)
        await pilot.pause()

        assert len(chat_log.lines) > lines_before
        assert any("new.py" in str(line) for line in chat_log.lines)'''

content = content.replace(old_test2, new_test2)

# Update test_render_event_still_routes_generic_flags_to_live_pane_as_before
old_test3 = '''@pytest.mark.asyncio
async def test_render_event_still_routes_generic_flags_to_live_pane_as_before():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)
        events_log = app.query_one("#events-log", RichLog)
        lines_before_atelier = len(atelier.lines)

        raw = json.dumps({
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "trace-start-d",
            "payload": {},
        })
        app._render_event(raw)
        await pilot.pause()

        assert len(events_log.lines) > 0'''

new_test3 = '''@pytest.mark.asyncio
async def test_render_event_still_routes_generic_flags_to_chat():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat_log = app.query_one("#chat-log", RichLog)
        lines_before = len(chat_log.lines)

        raw = json.dumps({
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "trace-start-d",
            "payload": {},
        })
        app._render_event(raw)
        await pilot.pause()

        assert len(chat_log.lines) > lines_before'''

content = content.replace(old_test3, new_test3)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'w') as f:
    f.write(content)
print("Updated atelier live tests")