"""Tests for the cloud_mode.py toggle -- off by default, explicit on/off."""
from __future__ import annotations

from sovereign_agent.cloud_mode import is_cloud_mode_enabled, set_cloud_mode


def test_disabled_by_default_when_no_flag_file(tmp_path):
    assert is_cloud_mode_enabled(tmp_path) is False


def test_set_enabled_true_persists(tmp_path):
    set_cloud_mode(True, data_dir=tmp_path)
    assert is_cloud_mode_enabled(tmp_path) is True


def test_set_enabled_false_persists(tmp_path):
    set_cloud_mode(True, data_dir=tmp_path)
    set_cloud_mode(False, data_dir=tmp_path)
    assert is_cloud_mode_enabled(tmp_path) is False


def test_corrupt_flag_file_reads_as_disabled_not_a_crash(tmp_path):
    p = tmp_path / "cloud_mode.json"
    p.write_text("not json{{{", encoding="utf-8")
    assert is_cloud_mode_enabled(tmp_path) is False
