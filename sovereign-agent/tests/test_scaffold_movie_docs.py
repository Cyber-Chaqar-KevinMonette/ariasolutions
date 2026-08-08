"""Tests for scaffold_movie_docs — real starter docs generated into a movie
project's own workspace, pulling live data from its record."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import MovieProject, save
from sovereign_agent.tools.scaffold_movie_docs import ScaffoldMovieDocsTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "scaffold_movie_docs" in _TIER_REGISTRY
    assert _TIER_REGISTRY["scaffold_movie_docs"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "scaffold_movie_docs" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = ScaffoldMovieDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_writes_both_docs_into_the_project_workspace(tmp_path):
    save(MovieProject(
        title="Test Film", genre="short-film",
        logline="one clean visual idea", monetization_note="tips jar",
    ), tmp_path)
    tool = ScaffoldMovieDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="test-film"), trace_id="t1")
    assert result.ok

    from pathlib import Path
    treatment = Path(result.output["treatment_path"])
    outline = Path(result.output["script_outline_path"])
    assert treatment.is_file()
    assert outline.is_file()


@pytest.mark.asyncio
async def test_treatment_uses_real_project_data_not_generic_filler(tmp_path):
    save(MovieProject(
        title="Neon Drift", genre="music-video",
        logline="visuals built to the beat, one clean idea",
        monetization_note="Bandcamp tie-in",
    ), tmp_path)
    tool = ScaffoldMovieDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="neon-drift"), trace_id="t1")

    from pathlib import Path
    text = Path(result.output["treatment_path"]).read_text(encoding="utf-8")
    assert "Neon Drift" in text
    assert "Music video" in text
    assert "visuals built to the beat, one clean idea" in text
    assert "Bandcamp tie-in" in text


@pytest.mark.asyncio
async def test_treatment_prompts_for_missing_logline_rather_than_blank(tmp_path):
    save(MovieProject(title="Blank Slate"), tmp_path)
    tool = ScaffoldMovieDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="blank-slate"), trace_id="t1")

    from pathlib import Path
    text = Path(result.output["treatment_path"]).read_text(encoding="utf-8")
    assert "not written yet" in text
    assert "not decided yet" in text


@pytest.mark.asyncio
async def test_rerunning_refreshes_rather_than_duplicates(tmp_path):
    save(MovieProject(title="Refresh Me", logline="ORIGINAL_LOGLINE_TEXT"), tmp_path)
    tool = ScaffoldMovieDocsTool(data_dir=tmp_path)
    await tool.execute(tool.Args(project_slug="refresh-me"), trace_id="t1")

    save(MovieProject(title="Refresh Me", logline="UPDATED_LOGLINE_TEXT"), tmp_path)
    r2 = await tool.execute(tool.Args(project_slug="refresh-me"), trace_id="t2")

    from pathlib import Path
    text = Path(r2.output["treatment_path"]).read_text(encoding="utf-8")
    assert "UPDATED_LOGLINE_TEXT" in text
    assert "ORIGINAL_LOGLINE_TEXT" not in text  # overwritten, not appended


@pytest.mark.asyncio
async def test_records_the_treatment_in_the_asset_manifest(tmp_path):
    save(MovieProject(title="Manifest Check"), tmp_path)
    tool = ScaffoldMovieDocsTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="manifest-check"), trace_id="t1")

    from pathlib import Path
    workspace = Path(result.output["treatment_path"]).parent
    manifest = (workspace / "ASSET_MANIFEST.md").read_text(encoding="utf-8")
    assert "TREATMENT.md" in manifest
    assert "scaffold_movie_docs" in manifest
