"""Tests for scaffold_game_docs — real starter docs generated into a game
project's own workspace, pulling live data from its record."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import GameProject, save
from sovereign_agent.tools.scaffold_game_docs import ScaffoldGameDocsTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "scaffold_game_docs" in _TIER_REGISTRY
    assert _TIER_REGISTRY["scaffold_game_docs"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "scaffold_game_docs" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = ScaffoldGameDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_writes_both_docs_into_the_project_workspace(tmp_path):
    save(GameProject(
        project_name="Prestige Clicker", genre="idle-incremental",
        concept="one core loop, replayed", monetization_note="itch.io PWYW",
    ), tmp_path)
    tool = ScaffoldGameDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="prestige-clicker"), trace_id="t1")
    assert result.ok

    from pathlib import Path
    brief = Path(result.output["brief_path"])
    started = Path(result.output["getting_started_path"])
    assert brief.is_file()
    assert started.is_file()


@pytest.mark.asyncio
async def test_brief_uses_real_project_data_not_generic_filler(tmp_path):
    save(GameProject(
        project_name="Neon Drift", genre="arcade-score-attack",
        concept="60-second runs, one mechanic done well",
        monetization_note="Steam, $100 fee covered once we ship",
    ), tmp_path)
    tool = ScaffoldGameDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="neon-drift"), trace_id="t1")

    from pathlib import Path
    brief_text = Path(result.output["brief_path"]).read_text(encoding="utf-8")
    assert "Neon Drift" in brief_text
    assert "Arcade / score-attack" in brief_text
    assert "60-second runs, one mechanic done well" in brief_text
    assert "Steam, $100 fee covered once we ship" in brief_text


@pytest.mark.asyncio
async def test_brief_prompts_for_missing_concept_rather_than_blank(tmp_path):
    save(GameProject(project_name="Blank Slate"), tmp_path)
    tool = ScaffoldGameDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="blank-slate"), trace_id="t1")

    from pathlib import Path
    brief_text = Path(result.output["brief_path"]).read_text(encoding="utf-8")
    assert "not written yet" in brief_text
    assert "not decided yet" in brief_text


@pytest.mark.asyncio
async def test_getting_started_documents_the_real_tool_names(tmp_path):
    save(GameProject(project_name="Any Project"), tmp_path)
    tool = ScaffoldGameDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="any-project"), trace_id="t1")

    from pathlib import Path
    text = Path(result.output["getting_started_path"]).read_text(encoding="utf-8")
    for tool_name in ("godot_check", "godot_export", "godot_open",
                     "download_game_asset", "award_game_xp", "set_game_focus"):
        assert tool_name in text


@pytest.mark.asyncio
async def test_rerunning_refreshes_rather_than_duplicates(tmp_path):
    save(GameProject(project_name="Refresh Me", concept="ORIGINAL_CONCEPT_TEXT"), tmp_path)
    tool = ScaffoldGameDocsTool(data_dir=tmp_path)
    await tool.execute(tool.Args(project_slug="refresh-me"), trace_id="t1")

    save(GameProject(project_name="Refresh Me", concept="UPDATED_CONCEPT_TEXT"), tmp_path)
    r2 = await tool.execute(tool.Args(project_slug="refresh-me"), trace_id="t2")

    from pathlib import Path
    text = Path(r2.output["brief_path"]).read_text(encoding="utf-8")
    assert "UPDATED_CONCEPT_TEXT" in text
    assert "ORIGINAL_CONCEPT_TEXT" not in text  # overwritten, not appended
