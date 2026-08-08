"""Tests for movie-studio-d — storage-aware movie asset tracking."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_assets import (
    ASSET_KINDS,
    BudgetStatus,
    asset_manifest_path,
    check_workspace_budget,
    record_asset,
)


def test_asset_kinds_covers_script_storyboard_clip_and_episode_cut():
    # "clip" is here so Phase 2 (real local video generation) has nothing
    # to add; "episode_cut" (movie-focus-d, Phase 3C) is the ffmpeg-
    # assembled merge of a completed episode's clips.
    assert ASSET_KINDS == {"script", "storyboard", "clip", "episode_cut"}


def test_budget_status_math():
    b = BudgetStatus(used_bytes=100 * 1024 * 1024, budget_bytes=500 * 1024 * 1024)
    assert not b.over_budget
    assert b.used_mb == 100.0
    assert b.budget_mb == 500.0
    assert b.remaining_bytes == 400 * 1024 * 1024

    over = BudgetStatus(used_bytes=600 * 1024 * 1024, budget_bytes=500 * 1024 * 1024)
    assert over.over_budget
    assert over.remaining_bytes == 0


def test_check_workspace_budget_measures_real_files(tmp_path):
    (tmp_path / "storyboards").mkdir()
    (tmp_path / "storyboards" / "a.png").write_bytes(b"x" * 1000)
    (tmp_path / "storyboards" / "b.png").write_bytes(b"x" * 2000)
    status = check_workspace_budget(tmp_path, budget_bytes=10_000)
    assert status.used_bytes == 3000
    assert not status.over_budget

    tight = check_workspace_budget(tmp_path, budget_bytes=2000)
    assert tight.over_budget


def test_check_workspace_budget_missing_dir_is_zero(tmp_path):
    status = check_workspace_budget(tmp_path / "does-not-exist")
    assert status.used_bytes == 0


def test_record_asset_writes_manifest(tmp_path):
    path = record_asset(
        tmp_path, relative_path="storyboards/scene1.png",
        kind="storyboard", source_tool="generate_storyboard_image",
    )
    assert path == asset_manifest_path(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "scene1.png" in text
    assert "storyboard" in text
    assert "generate_storyboard_image" in text


def test_record_asset_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError, match="unknown asset kind"):
        record_asset(tmp_path, relative_path="x.png", kind="soundtrack",
                     source_tool="whatever")


def test_record_asset_appends_not_overwrites(tmp_path):
    record_asset(tmp_path, relative_path="a.png", kind="storyboard",
                source_tool="generate_storyboard_image")
    record_asset(tmp_path, relative_path="script.md", kind="script",
                source_tool="scaffold_movie_docs")
    text = asset_manifest_path(tmp_path).read_text(encoding="utf-8")
    assert "a.png" in text and "script.md" in text
