#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_cockpit.py', 'r') as f:
    content = f.read()

# Update test_cockpit_launches_and_renders
old_test1 = '''@pytest.mark.asyncio
async def test_cockpit_launches_and_renders():
    """The most basic invariant: the app must render without crashing."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        # Let the on_mount handler complete.
        await pilot.pause()
        # The four core widgets must be reachable.
        chat = app.query_one("#chat-log")
        events = app.query_one("#events-log")
        input_box = app.query_one("#input-box")
        status = app.query_one("#status-bar")
        assert chat is not None
        assert events is not None
        assert input_box is not None
        assert status is not None'''

new_test1 = '''@pytest.mark.asyncio
async def test_cockpit_launches_and_renders():
    """The most basic invariant: the app must render without crashing."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        # Let the on_mount handler complete.
        await pilot.pause()
        # The unified chat window and core widgets must be reachable.
        chat = app.query_one("#chat-log")
        input_box = app.query_one("#input-box")
        status = app.query_one("#status-bar")
        header = app.query_one("#memory-metrics-header")
        assert chat is not None
        assert input_box is not None
        assert status is not None
        assert header is not None'''

content = content.replace(old_test1, new_test1)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_cockpit.py', 'w') as f:
    f.write(content)
print("Updated test_cockpit_launches_and_renders")