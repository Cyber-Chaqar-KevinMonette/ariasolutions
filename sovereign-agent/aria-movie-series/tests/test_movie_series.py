"""Tests for movie_series — Series + Season, sitting above movie_projects.py."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_series import (
    Season,
    Series,
    add_episode_to_season,
    create_season,
    get_episode_focus,
    list_all_series,
    list_seasons,
    load_season,
    load_series,
    load_series_by_slug,
    parse_season_id,
    season_id_for,
    set_episode_focus,
    slugify,
    validate_series,
)


def test_slugify_basic():
    assert slugify("My Great Series!") == "my-great-series"
    assert slugify("") == "series"


def test_validate_series_rejects_missing_title():
    errs = validate_series(Series(title=""))
    assert any("title" in e for e in errs)


def test_validate_series_rejects_bad_genre():
    errs = validate_series(Series(title="Ok", genre="bogus"))
    assert any("genre" in e for e in errs)


def test_save_and_load_series_roundtrip(tmp_path):
    from sovereign_agent.movie_series import save_series
    s = Series(title="Neon Skyline", logline="a city that dreams back")
    save_series(s, tmp_path)
    loaded = load_series("Neon Skyline", tmp_path)
    assert loaded is not None
    assert loaded.logline == "a city that dreams back"
    assert loaded.slug == "neon-skyline"
    assert loaded.created_at and loaded.modified_at


def test_save_series_invalid_raises(tmp_path):
    from sovereign_agent.movie_series import save_series
    with pytest.raises(ValueError):
        save_series(Series(title=""), tmp_path)


def test_load_series_by_slug_and_list_all(tmp_path):
    from sovereign_agent.movie_series import save_series
    save_series(Series(title="Alpha"), tmp_path)
    save_series(Series(title="Beta"), tmp_path)
    assert load_series_by_slug("alpha", tmp_path) is not None
    all_series = list_all_series(tmp_path)
    assert {s.title for s in all_series} == {"Alpha", "Beta"}


def test_create_season_requires_existing_series(tmp_path):
    with pytest.raises(ValueError):
        create_season("no-such-series", "Season One", tmp_path)


def test_create_season_appends_to_series_and_stores_season(tmp_path):
    from sovereign_agent.movie_series import save_series
    save_series(Series(title="Gamma"), tmp_path)

    season = create_season("gamma", "Season One", tmp_path)
    assert season.season_number == 1
    assert season.season_id == season_id_for("gamma", 1)

    series = load_series_by_slug("gamma", tmp_path)
    assert series.season_ids == [season.season_id]

    season2 = create_season("gamma", "Season Two", tmp_path)
    assert season2.season_number == 2
    series = load_series_by_slug("gamma", tmp_path)
    assert series.season_ids == [season.season_id, season2.season_id]


def test_parse_season_id_roundtrip():
    sid = season_id_for("my-series", 3)
    parsed = parse_season_id(sid)
    assert parsed == ("my-series", 3)


def test_parse_season_id_rejects_malformed():
    assert parse_season_id("not-a-season-id") is None


def test_load_season_and_list_seasons(tmp_path):
    from sovereign_agent.movie_series import save_series
    save_series(Series(title="Delta"), tmp_path)
    s1 = create_season("delta", "S1", tmp_path)
    create_season("delta", "S2", tmp_path)

    loaded = load_season(s1.season_id, tmp_path)
    assert loaded is not None
    assert loaded.title == "S1"

    seasons = list_seasons("delta", tmp_path)
    assert [s.title for s in seasons] == ["S1", "S2"]


def test_add_episode_to_season_is_idempotent(tmp_path):
    from sovereign_agent.movie_series import save_series
    save_series(Series(title="Epsilon"), tmp_path)
    season = create_season("epsilon", "S1", tmp_path)

    add_episode_to_season(season.season_id, "ep-epsilon-s01-e01-abc1234", tmp_path)
    add_episode_to_season(season.season_id, "ep-epsilon-s01-e01-abc1234", tmp_path)  # duplicate, ignored
    updated = load_season(season.season_id, tmp_path)
    assert updated.episode_ids == ["ep-epsilon-s01-e01-abc1234"]


def test_add_episode_to_season_missing_season_raises(tmp_path):
    with pytest.raises(ValueError):
        add_episode_to_season("no-such-series-s01", "ep-x", tmp_path)


def test_get_episode_focus_defaults_to_none(tmp_path):
    focus = get_episode_focus(tmp_path)
    assert focus.episode_id is None
    assert focus.history == []


def test_set_episode_focus_requires_a_reason(tmp_path):
    with pytest.raises(ValueError):
        set_episode_focus("ep-x-s01-e01-abc1234", "", tmp_path)


def test_set_episode_focus_roundtrip_and_history(tmp_path):
    focus = set_episode_focus("ep-x-s01-e01-abc1234", "starting the pilot", tmp_path)
    assert focus.episode_id == "ep-x-s01-e01-abc1234"
    assert focus.since

    reloaded = get_episode_focus(tmp_path)
    assert reloaded.episode_id == "ep-x-s01-e01-abc1234"
    assert reloaded.history[-1]["reason"] == "starting the pilot"
    assert reloaded.history[-1]["from"] is None

    focus2 = set_episode_focus("ep-x-s01-e02-def5678", "moving to episode 2", tmp_path)
    assert focus2.episode_id == "ep-x-s01-e02-def5678"
    assert focus2.history[-1]["from"] == "ep-x-s01-e01-abc1234"


def test_unbounded_episodes_per_season(tmp_path):
    """Kevin: 'Each season can have as many episodes as we want' — the data
    model itself must never cap this."""
    from sovereign_agent.movie_series import save_series
    save_series(Series(title="Zeta"), tmp_path)
    season = create_season("zeta", "S1", tmp_path)
    for i in range(50):
        add_episode_to_season(season.season_id, f"ep-zeta-s01-e{i:02d}-abc1234", tmp_path)
    updated = load_season(season.season_id, tmp_path)
    assert len(updated.episode_ids) == 50
