"""Tests for game_design_doctrine — the Godot game-design expertise data
threaded into game_design_brief.py's prompts."""
from __future__ import annotations

from sovereign_agent.game_design_doctrine import (
    DIMENSION_ENGINE_NOTES,
    GENRE_DESIGN_NOTES,
    GODOT_CORE_PRINCIPLES,
    notes_for,
)
from sovereign_agent.game_projects import DIMENSIONS, GENRES, GameProject


def test_every_genre_has_design_notes():
    for key, _label in GENRES:
        assert key in GENRE_DESIGN_NOTES
        assert len(GENRE_DESIGN_NOTES[key]) > 40


def test_every_dimension_has_engine_notes():
    for key, _label in DIMENSIONS:
        assert key in DIMENSION_ENGINE_NOTES
        assert len(DIMENSION_ENGINE_NOTES[key]) > 40


def test_core_principles_nonempty():
    assert len(GODOT_CORE_PRINCIPLES) >= 3
    assert all(isinstance(p, str) and p for p in GODOT_CORE_PRINCIPLES)


def test_notes_for_threads_genre_and_dimension():
    project = GameProject(project_name="Test Game", genre="platformer", dimension="3d")
    notes = notes_for(project)
    assert GENRE_DESIGN_NOTES["platformer"] in notes
    assert DIMENSION_ENGINE_NOTES["3d"] in notes
    for principle in GODOT_CORE_PRINCIPLES:
        assert principle in notes


def test_notes_for_falls_back_for_unknown_genre():
    project = GameProject(project_name="Test Game", genre="other", genre_other="tower defense",
                          dimension="2d")
    notes = notes_for(project)
    assert GENRE_DESIGN_NOTES["other"] in notes
