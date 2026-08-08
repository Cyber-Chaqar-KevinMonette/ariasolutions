"""Tests for movie-studio-d — the Movie Project Studio store + focus discipline."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import (
    MOVIE_GENRES,
    MovieProject,
    delete,
    get_focus,
    list_all,
    load,
    load_by_slug,
    movie_workspace_dir,
    projects_dir,
    save,
    set_focus,
    slugify,
    validate,
)


# ── model / validation ─────────────────────────────────────────────────────
def test_genre_label_uses_catalog_then_other():
    p = MovieProject(title="x", genre="documentary-style")
    assert p.genre_label == "Documentary-style"
    o = MovieProject(title="x", genre="other", genre_other="Anthology")
    assert o.genre_label == "Anthology"


def test_style_label_uses_catalog():
    assert MovieProject(title="x", style="live-action").style_label == "Live-action"


def test_validate_requires_title():
    assert any("required" in e for e in validate(MovieProject(title="")))


def test_validate_rejects_bad_title_chars():
    assert validate(MovieProject(title="../etc"))


def test_validate_rejects_unknown_genre():
    assert validate(MovieProject(title="ok", genre="not-a-genre"))


def test_validate_other_needs_genre_other():
    assert validate(MovieProject(title="ok", genre="other", genre_other=""))
    assert not validate(MovieProject(title="ok", genre="other", genre_other="thing"))


def test_validate_rejects_unknown_style():
    assert validate(MovieProject(title="ok", style="not-a-style"))


def test_validate_rejects_unknown_status():
    assert validate(MovieProject(title="ok", status="not-a-status"))


def test_genres_has_other_last():
    assert MOVIE_GENRES[-1][0] == "other"


def test_style_defaults_to_animated():
    assert MovieProject(title="x").style == "animated"


# ── store round-trip ────────────────────────────────────────────────────────
def test_save_load_round_trip(tmp_path):
    p = MovieProject(title="Test Film", genre="short-film",
                     logline="one clean visual idea")
    save(p, tmp_path)
    got = load("Test Film", tmp_path)
    assert got is not None
    assert got.genre == "short-film"
    assert got.created_at and got.modified_at


def test_load_by_slug(tmp_path):
    save(MovieProject(title="Test Film"), tmp_path)
    got = load_by_slug(slugify("Test Film"), tmp_path)
    assert got is not None and got.title == "Test Film"
    assert load_by_slug("does-not-exist", tmp_path) is None


def test_save_invalid_raises(tmp_path):
    with pytest.raises(ValueError):
        save(MovieProject(title=""), tmp_path)


def test_list_all_sorted_and_multiple_and_skips_focus_file(tmp_path):
    save(MovieProject(title="Alpha"), tmp_path)
    save(MovieProject(title="Beta"), tmp_path)
    set_focus(slugify("Alpha"), "testing", tmp_path)
    titles = [p.title for p in list_all(tmp_path)]
    assert titles == ["Alpha", "Beta"]  # _focus.json never shows up as a project


def test_delete(tmp_path):
    save(MovieProject(title="Gone"), tmp_path)
    assert delete("Gone", tmp_path) is True
    assert load("Gone", tmp_path) is None
    assert delete("Gone", tmp_path) is False


def test_corrupt_file_is_skipped(tmp_path):
    save(MovieProject(title="Good"), tmp_path)
    (projects_dir(tmp_path) / "broken.json").write_text("{not json", encoding="utf-8")
    got = list_all(tmp_path)
    assert [p.title for p in got] == ["Good"]


def test_slugify_is_path_safe():
    assert slugify("../../etc/passwd") == "etc-passwd"
    assert slugify("") == "movie"


def test_movie_workspace_dir_is_under_sandbox(tmp_path):
    d = movie_workspace_dir("my-slug", sandbox_dir=tmp_path)
    assert d == tmp_path / "movies" / "my-slug"
    assert d.is_dir()


# ── focus discipline ─────────────────────────────────────────────────────
def test_get_focus_defaults_to_none(tmp_path):
    f = get_focus(tmp_path)
    assert f.slug is None
    assert f.history == []


def test_set_focus_requires_reason(tmp_path):
    save(MovieProject(title="Alpha"), tmp_path)
    with pytest.raises(ValueError, match="reason"):
        set_focus(slugify("Alpha"), "", tmp_path)


def test_set_focus_requires_real_project(tmp_path):
    with pytest.raises(ValueError, match="no movie project"):
        set_focus("does-not-exist", "operator asked", tmp_path)


def test_set_focus_records_history(tmp_path):
    save(MovieProject(title="Alpha"), tmp_path)
    save(MovieProject(title="Beta"), tmp_path)
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
    save(MovieProject(title="Alpha"), tmp_path)
    for i in range(60):
        set_focus(slugify("Alpha"), f"switch {i}", tmp_path)
    f = get_focus(tmp_path)
    assert len(f.history) <= 50
