"""Tests for cockpit/game_window_pref.py — the optional-visual toggle.

Kevin, 2026-07-25: "make the game menu optional because it is kinda
wasting space. An optional visual." Visible by default (a real feature,
not hidden until discovered); persisted so a hide choice survives a
cockpit restart.
"""
from __future__ import annotations

from sovereign_agent.cockpit.game_window_pref import is_visible, set_visible


def test_visible_by_default(tmp_path):
    assert is_visible(tmp_path) is True


def test_set_hidden_persists(tmp_path):
    set_visible(False, data_dir=tmp_path)
    assert is_visible(tmp_path) is False


def test_set_visible_again_persists(tmp_path):
    set_visible(False, data_dir=tmp_path)
    set_visible(True, data_dir=tmp_path)
    assert is_visible(tmp_path) is True


def test_corrupt_file_reads_as_visible_not_a_crash(tmp_path):
    p = tmp_path / "game_window_pref.json"
    p.write_text("not json{{{", encoding="utf-8")
    assert is_visible(tmp_path) is True
