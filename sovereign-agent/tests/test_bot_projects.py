"""Tests for bot-studio-d — the Bot Project Studio store (define before build)."""
from __future__ import annotations

import pytest

from sovereign_agent.bot_projects import (
    BOT_KINDS,
    BotProject,
    compose_bots_report,
    delete,
    is_bots_query,
    list_all,
    load,
    projects_dir,
    save,
    slugify,
    validate,
)


# ── model / validation ─────────────────────────────────────────────────────
def test_kind_label_uses_catalog_then_other():
    p = BotProject(project_name="x", kind="restock-alert")
    assert p.kind_label == "Restock / price-alert"
    o = BotProject(project_name="x", kind="other", kind_other="Music queue")
    assert o.kind_label == "Music queue"


def test_validate_requires_name():
    assert any("required" in e for e in validate(BotProject(project_name="")))


def test_validate_rejects_bad_name_chars():
    assert validate(BotProject(project_name="../etc"))


def test_validate_rejects_unknown_kind():
    assert validate(BotProject(project_name="ok", kind="not-a-kind"))


def test_validate_other_needs_kind_other():
    assert validate(BotProject(project_name="ok", kind="other", kind_other=""))
    assert not validate(BotProject(project_name="ok", kind="other", kind_other="thing"))


def test_bot_kinds_has_other_last():
    assert BOT_KINDS[-1][0] == "other"


# ── store round-trip ────────────────────────────────────────────────────────
def test_save_load_round_trip(tmp_path):
    p = BotProject(project_name="Pokemon Restock", bot_name="StockScout",
                   kind="restock-alert", description="alert on restocks")
    save(p, tmp_path)
    got = load("Pokemon Restock", tmp_path)
    assert got is not None
    assert got.bot_name == "StockScout"
    assert got.kind == "restock-alert"
    assert got.created_at and got.modified_at


def test_save_invalid_raises(tmp_path):
    with pytest.raises(ValueError):
        save(BotProject(project_name=""), tmp_path)


def test_list_all_sorted_and_multiple(tmp_path):
    save(BotProject(project_name="Alpha", kind="community-mod"), tmp_path)
    save(BotProject(project_name="Beta", kind="support-ticket"), tmp_path)
    names = [p.project_name for p in list_all(tmp_path)]
    assert names == ["Alpha", "Beta"]


def test_delete(tmp_path):
    save(BotProject(project_name="Gone", kind="other", kind_other="x"), tmp_path)
    assert delete("Gone", tmp_path) is True
    assert load("Gone", tmp_path) is None
    assert delete("Gone", tmp_path) is False


def test_corrupt_file_is_skipped(tmp_path):
    save(BotProject(project_name="Good", kind="analytics-stats"), tmp_path)
    (projects_dir(tmp_path) / "broken.json").write_text("{not json", encoding="utf-8")
    got = list_all(tmp_path)
    assert [p.project_name for p in got] == ["Good"]


def test_slugify_is_path_safe():
    assert slugify("../../etc/passwd") == "etc-passwd"
    assert slugify("") == "project"


# ── chat bridge ─────────────────────────────────────────────────────────────
def test_is_bots_query():
    assert is_bots_query("what are we building?")
    assert is_bots_query("list our bots")
    assert not is_bots_query("how are you today")


def test_compose_report_empty(tmp_path):
    out = compose_bots_report(tmp_path)
    assert "/bots" in out and "No bot projects" in out


def test_compose_report_lists_projects(tmp_path):
    save(BotProject(project_name="Pikamon", bot_name="Scout",
                    kind="restock-alert", description="restock alerts"), tmp_path)
    out = compose_bots_report(tmp_path)
    assert "Pikamon" in out and "Scout" in out and "restock alerts" in out


# ── UI smoke (real cockpit, isolated tmp data dir via conftest) ──────────────
@pytest.mark.asyncio
async def test_bot_studio_opens_and_saves(tmp_path_factory):
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import BotStudioScreen
    from sovereign_agent.config import SETTINGS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_bot_studio()
        await pilot.pause()
        assert isinstance(app.screen, BotStudioScreen)
        app.screen.query_one("#bot-project-name", Input).value = "SmokeProj"
        app.screen.query_one("#bot-bot-name", Input).value = "SmokeBot"
        app.screen.query_one("#bot-description", Input).value = "a test concept"
        await pilot.click(app.screen.query_one("#bot-save-btn", Button))
        await pilot.pause()
        saved = load("SmokeProj", SETTINGS.paths.data_dir)
        assert saved is not None and saved.bot_name == "SmokeBot"


@pytest.mark.asyncio
async def test_bot_studio_browse_carousel():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import BotStudioScreen
    from sovereign_agent.config import SETTINGS

    save(BotProject(project_name="One", kind="community-mod"), SETTINGS.paths.data_dir)
    save(BotProject(project_name="Two", kind="support-ticket"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_bot_studio()
        await pilot.pause()
        assert isinstance(app.screen, BotStudioScreen)
        assert app.screen._pi == 0
        nxt = app.screen.query_one("#bot-next", Button)
        nxt.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(nxt)
        await pilot.pause()
        assert app.screen._pi == 1   # carousel advanced


@pytest.mark.asyncio
async def test_bot_studio_dryrun_button_is_safe(tmp_path_factory):
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import BotStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.discord_runtime.sources import Source, add_source

    save(BotProject(project_name="DryProj", kind="notification-feed"),
         SETTINGS.paths.data_dir)
    add_source(SETTINGS.paths.data_dir, "DryProj",
               Source(name="feed", url="http://x", allowed_min_interval_s=60))
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_bot_studio()
        await pilot.pause()
        assert isinstance(app.screen, BotStudioScreen)
        btn = app.screen.query_one("#bot-dryrun", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        # dry-run wrote an audit record and sent nothing
        from sovereign_agent.bot_projects import projects_dir
        from sovereign_agent.discord_runtime.sources import slugify
        runs = projects_dir(SETTINGS.paths.data_dir) / slugify("DryProj") / "runs.jsonl"
        assert runs.is_file()
