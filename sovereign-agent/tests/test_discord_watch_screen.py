"""UI smoke for 📡 Discord Watch + the /server-message owner command."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_discord_watch_opens_refreshes_and_closes(monkeypatch):
    import sovereign_agent.cockpit.discord_watch_screen as dws
    from sovereign_agent.cockpit import CockpitApp

    collected = []

    def fake_render(data_dir=None, limit=40):
        collected.append(limit)
        return "📡 Discord Watch — test snapshot"

    monkeypatch.setattr(dws, "render_activity", fake_render)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_discord_watch()
        await pilot.pause()
        assert isinstance(app.screen, dws.DiscordWatchScreen)
        # the off-thread collector ran (lesson 15: no disk on the UI thread)
        for _ in range(10):
            await pilot.pause(0.1)
            if collected:
                break
        assert collected and collected[0] == 40
        # toggle behavior: calling the action again closes it
        app.action_discord_watch()
        await pilot.pause()
        assert not isinstance(app.screen, dws.DiscordWatchScreen)


@pytest.mark.asyncio
async def test_server_message_posts_live_and_echoes(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp

    calls = []

    def fake_publish(data_dir, text, live=False):
        calls.append((text, live))
        return (True, "announcement posted to the server 👑")

    import sovereign_agent.advertising as adv
    monkeypatch.setattr(adv, "publish_announcement", fake_publish)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.run_server_message("Grand opening this weekend!")
        for _ in range(10):
            await pilot.pause(0.1)
            if calls:
                break
        assert calls == [("Grand opening this weekend!", True)]
        # empty text → usage hint, no post
        app.run_server_message("   ")
        await pilot.pause()
        assert len(calls) == 1
