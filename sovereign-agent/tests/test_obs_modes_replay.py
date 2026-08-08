"""obs-modes-d + replay-sanitize-d (Kevin, 2026-07-19): observability
modes (all windows vs chat+inbox focus) and the display-side purge that
keeps pre-ban diamonds + raw markup out of the replayed thread."""
import pytest


# ---------------- replay sanitizer ------------------------------------

def test_sanitize_strips_markup_and_purges_diamonds():
    from sovereign_agent.cockpit.app import sanitize_replay_text

    raw = "[dim]◈ resume any time: /resume sess_23a[/dim]"
    out = sanitize_replay_text(raw)
    assert "[dim]" not in out and "[/dim]" not in out
    assert "◈" not in out
    assert "◊ resume any time" in out


def test_sanitize_preserves_uppercase_bracket_ids():
    from sovereign_agent.cockpit.app import sanitize_replay_text

    out = sanitize_replay_text("[bold red]inbox [HH852Q] filed[/bold red]")
    assert "[HH852Q]" in out
    assert "bold red" not in out


def test_purge_covers_the_whole_diamond_family():
    from sovereign_agent.glyphs import purge_unsafe_diamonds

    assert purge_unsafe_diamonds("a◈b◆c◇d♦e") == "a◊b◊c◊d◊e"
    assert purge_unsafe_diamonds("clean ◊ text") == "clean ◊ text"


# ---------------- observability modes ---------------------------------

@pytest.mark.asyncio
async def test_obs_focus_hides_memory_and_atelier_but_keeps_live(tmp_path,
                                                                 monkeypatch):
    """Kevin, 2026-07-21: "I was saying we should add a third window" --
    obs-focus used to hide live-pane along with memory/atelier (chat+inbox
    only, 2 windows); live-pane now joins chat+inbox (3 windows).
    Memory + atelier stay hidden -- that's still the "focus" of focus mode."""
    from sovereign_agent.cockpit.app import CockpitApp

    monkeypatch.setenv("HOME", str(tmp_path))
    app = CockpitApp()
    async with app.run_test(size=(160, 48)):
        main = app.query_one("#main")
        assert not main.has_class("obs-focus")          # default: all
        app.action_obs_mode("focus")
        assert main.has_class("obs-focus")
        for pane in ("#memory-pane", "#atelier-pane"):
            assert app.query_one(pane).styles.display == "none"
        assert app.query_one("#chat-pane").styles.display != "none"
        assert app.query_one("#inbox-pane").styles.display != "none"
        assert app.query_one("#live-pane").styles.display != "none"
        app.action_obs_mode()                            # bare = toggle back
        assert not main.has_class("obs-focus")
        for pane in ("#memory-pane", "#live-pane", "#atelier-pane"):
            assert app.query_one(pane).styles.display != "none"


@pytest.mark.asyncio
async def test_obs_pref_persists_and_restores(tmp_path, monkeypatch):
    import json

    from sovereign_agent.cockpit.app import CockpitApp

    monkeypatch.setenv("HOME", str(tmp_path))
    app = CockpitApp()
    async with app.run_test(size=(160, 48)):
        app.action_obs_mode("focus")
        pref = json.loads(app._layout_pref_path().read_text())
        assert pref["obs"] == "focus"
    app2 = CockpitApp()
    async with app2.run_test(size=(160, 48)):
        assert app2.query_one("#main").has_class("obs-focus")
