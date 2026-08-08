#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'r') as f:
    content = f.read()

# Update test_render_work_event_colorizes_edit_with_diff_lines
old_test = '''@pytest.mark.asyncio
async def test_render_work_event_colorizes_edit_with_diff_lines():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#chat-log", RichLog)

        ev = {
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-edit",
            "payload": {
                "op": "edit",
                "path": "/tmp/mod.py",
                "added": 2,
                "removed": 1,
                "diff_excerpt": "+new line\n-old line\n context",
            },
        }
        app._render_work_event(ev)
        await pilot.pause()

        rendered = "\\n".join(str(line) for line in atelier.lines)
        assert "mod.py" in rendered
        assert "new line" in rendered
        assert "old line" in rendered'''

new_test = '''@pytest.mark.asyncio
async def test_render_work_event_colorizes_edit_with_diff_lines():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#chat-log", RichLog)

        ev = {
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-edit",
            "payload": {
                "op": "edit",
                "path": "/tmp/mod.py",
                "added": 2,
                "removed": 1,
                "diff_excerpt": "+new line\\n-old line\\n context",
            },
        }
        app._render_work_event(ev)
        await pilot.pause()

        rendered = "\\n".join(str(line) for line in atelier.lines)
        # Work event should appear in the chat
        assert "mod.py" in rendered, f"mod.py not found in chat. Chat has {len(atelier.lines)} lines. Last 3: {[str(l)[:50] for l in atelier.lines[-3:]]}"
        assert "new line" in rendered
        assert "old line" in rendered'''

content = content.replace(old_test, new_test)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_atelier_live.py', 'w') as f:
    f.write(content)
print("Updated test with better error message")