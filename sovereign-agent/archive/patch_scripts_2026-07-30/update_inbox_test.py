#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_cockpit.py', 'r') as f:
    content = f.read()

# Update test_inbox_pane_exists_and_renders_requests
old_test = '''@pytest.mark.asyncio
async def test_inbox_pane_exists_and_renders_requests():
    """v0.2.37.0 — the 4th window (◊ inbox) must exist and render the
    collaboration requests filed in the store."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore

    rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
    rs.open("question", "What database should I use?")
    done = rs.open("suggestion", "Add a cache layer")
    rs.resolve(done.request_id)

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        inbox = app.query_one("#inbox-log")
        assert inbox is not None
        app._refresh_inbox_pane()
        await pilot.pause()
        # The pane rendered content (open item + recent section).
        assert len(inbox.lines) > 0'''

new_test = '''@pytest.mark.asyncio
async def test_inbox_pane_exists_and_renders_requests():
    """v0.2.37.0 — inbox content is now rendered in the unified chat.
    The collaboration requests filed in the store should appear in chat."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore

    rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
    rs.open("question", "What database should I use?")
    done = rs.open("suggestion", "Add a cache layer")
    rs.resolve(done.request_id)

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        chat = app.query_one("#chat-log")
        assert chat is not None
        app._refresh_inbox_pane()
        await pilot.pause()
        # The chat rendered inbox content.
        assert len(chat.lines) > 0'''

content = content.replace(old_test, new_test)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_cockpit.py', 'w') as f:
    f.write(content)
print("Updated test_inbox_pane_exists_and_renders_requests")