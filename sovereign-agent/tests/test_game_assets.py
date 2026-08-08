"""Tests for game-studio-d — license-safe + storage-aware game assets."""
from __future__ import annotations

from sovereign_agent.game_assets import (
    ALLOWED_ASSET_DOMAINS,
    ALLOWED_LICENSES,
    BudgetStatus,
    asset_licenses_path,
    check_workspace_budget,
    domain_allowed,
    record_asset,
    validate_license,
)


def test_allowed_licenses_excludes_nc():
    # No non-commercial-only license is ever allowed — the goal is real revenue.
    for lic in ALLOWED_LICENSES:
        assert "NC" not in lic


def test_validate_license_accepts_allowlisted():
    assert validate_license("CC0") == []
    assert validate_license("public-domain") == []
    assert validate_license("CC-BY") == []


def test_validate_license_refuses_unknown():
    errs = validate_license("CC-BY-NC")
    assert errs
    assert "CC-BY-NC" in errs[0]


def test_domain_allowed_exact_and_subdomain():
    assert domain_allowed("kenney.nl")
    assert domain_allowed("opengameart.org")
    assert domain_allowed("freesound.org")
    assert domain_allowed("assets.kenney.nl")  # subdomain of an allowlisted domain
    assert not domain_allowed("evil.com")
    assert not domain_allowed("notkenney.nl")  # NOT a subdomain — must not match by substring


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
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.wav").write_bytes(b"x" * 1000)
    (tmp_path / "assets" / "b.wav").write_bytes(b"x" * 2000)
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
        tmp_path, relative_path="assets/audio/jump.wav",
        source_url="https://kenney.nl/assets/jump.wav",
        license_id="CC0",
    )
    assert path == asset_licenses_path(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "jump.wav" in text
    assert "CC0" in text
    assert "kenney.nl" in text


def test_record_asset_includes_attribution_when_cc_by(tmp_path):
    path = record_asset(
        tmp_path, relative_path="assets/audio/loop.ogg",
        source_url="https://opengameart.org/x",
        license_id="CC-BY", attribution="Jane Doe, OpenGameArt",
    )
    text = path.read_text(encoding="utf-8")
    assert "attribution: Jane Doe, OpenGameArt" in text


def test_record_asset_appends_not_overwrites(tmp_path):
    record_asset(tmp_path, relative_path="a.wav", source_url="u1", license_id="CC0")
    record_asset(tmp_path, relative_path="b.wav", source_url="u2", license_id="CC0")
    text = asset_licenses_path(tmp_path).read_text(encoding="utf-8")
    assert "a.wav" in text and "b.wav" in text
