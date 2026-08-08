"""Tests for game-studio-d — the Game Project Studio store + focus discipline."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import (
    DIMENSIONS,
    GENRES,
    GameProject,
    delete,
    game_workspace_dir,
    get_focus,
    list_all,
    load,
    load_by_slug,
    projects_dir,
    save,
    set_focus,
    slugify,
    validate,
)


# ── model / validation ─────────────────────────────────────────────────────
def test_genre_label_uses_catalog_then_other():
    p = GameProject(project_name="x", genre="puzzle")
    assert p.genre_label == "Puzzle (one-screen or short levels)"
    o = GameProject(project_name="x", genre="other", genre_other="Rhythm game")
    assert o.genre_label == "Rhythm game"


def test_validate_requires_name():
    assert any("required" in e for e in validate(GameProject(project_name="")))


def test_validate_rejects_bad_name_chars():
    assert validate(GameProject(project_name="../etc"))


def test_validate_rejects_unknown_genre():
    assert validate(GameProject(project_name="ok", genre="not-a-genre"))


# ── dimension-d ───────────────────────────────────────────────────────────
def test_dimension_defaults_to_2d():
    assert GameProject(project_name="x").dimension == "2d"


def test_dimension_covers_2d_2_5d_3d():
    keys = {k for k, _ in DIMENSIONS}
    assert keys == {"2d", "2.5d", "3d"}


def test_validate_rejects_unknown_dimension():
    assert validate(GameProject(project_name="ok", dimension="4d"))


def test_dimension_roundtrips_through_save_load(tmp_path):
    p = GameProject(project_name="Cube Runner", dimension="3d")
    save(p, tmp_path)
    loaded = load("Cube Runner", tmp_path)
    assert loaded is not None
    assert loaded.dimension == "3d"


def test_validate_other_needs_genre_other():
    assert validate(GameProject(project_name="ok", genre="other", genre_other=""))
    assert not validate(GameProject(project_name="ok", genre="other", genre_other="thing"))


def test_validate_rejects_unknown_status():
    assert validate(GameProject(project_name="ok", status="not-a-status"))


def test_genres_has_other_last():
    assert GENRES[-1][0] == "other"


def test_engine_defaults_to_godot():
    assert GameProject(project_name="x").engine == "godot"


# ── store round-trip ────────────────────────────────────────────────────────
def test_save_load_round_trip(tmp_path):
    p = GameProject(project_name="Prestige Clicker", genre="idle-incremental",
                    concept="one loop, replayed")
    save(p, tmp_path)
    got = load("Prestige Clicker", tmp_path)
    assert got is not None
    assert got.genre == "idle-incremental"
    assert got.created_at and got.modified_at


def test_load_by_slug(tmp_path):
    save(GameProject(project_name="Prestige Clicker"), tmp_path)
    got = load_by_slug(slugify("Prestige Clicker"), tmp_path)
    assert got is not None and got.project_name == "Prestige Clicker"
    assert load_by_slug("does-not-exist", tmp_path) is None


def test_save_invalid_raises(tmp_path):
    with pytest.raises(ValueError):
        save(GameProject(project_name=""), tmp_path)


def test_list_all_sorted_and_multiple_and_skips_focus_file(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    save(GameProject(project_name="Beta"), tmp_path)
    set_focus(slugify("Alpha"), "testing", tmp_path)
    names = [p.project_name for p in list_all(tmp_path)]
    assert names == ["Alpha", "Beta"]  # _focus.json never shows up as a project


def test_delete(tmp_path):
    save(GameProject(project_name="Gone"), tmp_path)
    assert delete("Gone", tmp_path) is True
    assert load("Gone", tmp_path) is None
    assert delete("Gone", tmp_path) is False


def test_corrupt_file_is_skipped(tmp_path):
    save(GameProject(project_name="Good"), tmp_path)
    (projects_dir(tmp_path) / "broken.json").write_text("{not json", encoding="utf-8")
    got = list_all(tmp_path)
    assert [p.project_name for p in got] == ["Good"]


def test_slugify_is_path_safe():
    assert slugify("../../etc/passwd") == "etc-passwd"
    assert slugify("") == "project"


def test_game_workspace_dir_is_under_sandbox(tmp_path):
    d = game_workspace_dir("my-slug", sandbox_dir=tmp_path)
    assert d == tmp_path / "games" / "my-slug"
    assert d.is_dir()


# ── focus discipline ─────────────────────────────────────────────────────
def test_get_focus_defaults_to_none(tmp_path):
    f = get_focus(tmp_path)
    assert f.slug is None
    assert f.history == []


def test_set_focus_requires_reason(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    with pytest.raises(ValueError, match="reason"):
        set_focus(slugify("Alpha"), "", tmp_path)


def test_set_focus_requires_real_project(tmp_path):
    with pytest.raises(ValueError, match="no game project"):
        set_focus("does-not-exist", "operator asked", tmp_path)


def test_set_focus_records_history(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    save(GameProject(project_name="Beta"), tmp_path)
    set_focus(slugify("Alpha"), "operator asked to start here", tmp_path)
    f1 = get_focus(tmp_path)
    assert f1.slug == slugify("Alpha")
    assert len(f1.history) == 1
    assert f1.history[0]["to"] == slugify("Alpha")
    assert f1.history[0]["from"] is None
    assert f1.history[0]["vital"] is False

    set_focus(slugify("Beta"), "vital: Alpha blocked on missing asset", tmp_path, vital=True)
    f2 = get_focus(tmp_path)
    assert f2.slug == slugify("Beta")
    assert len(f2.history) == 2
    assert f2.history[1]["from"] == slugify("Alpha")
    assert f2.history[1]["to"] == slugify("Beta")
    assert f2.history[1]["vital"] is True


def test_set_focus_history_is_bounded(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    for i in range(60):
        set_focus(slugify("Alpha"), f"switch {i}", tmp_path)
    f = get_focus(tmp_path)
    assert len(f.history) <= 50
