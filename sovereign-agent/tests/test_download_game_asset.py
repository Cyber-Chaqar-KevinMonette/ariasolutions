"""Tests for game-studio-d — download_game_asset: license-safe by
construction, domain-restricted, storage-aware, binary-capable (unlike
write_file, which is UTF-8-text-only)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
from sovereign_agent.tools.download_game_asset import DownloadGameAssetTool


def test_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "download_game_asset" in _TIER_REGISTRY
    assert _TIER_REGISTRY["download_game_asset"].tier == 1


def _fake_client(status_code=200, content=b"RIFF....WAVEfmt "):
    resp = MagicMock(status_code=status_code, content=content)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = DownloadGameAssetTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", url="https://kenney.nl/x.wav",
                 relative_path="a.wav", license_id="CC0"),
        trace_id="t1",
    )
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_domain_not_allowlisted_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = DownloadGameAssetTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", url="https://evil.com/x.wav",
                 relative_path="a.wav", license_id="CC0"),
        trace_id="t1",
    )
    assert not result.ok
    assert "domain_not_allowlisted" in result.error


@pytest.mark.asyncio
async def test_bad_license_refused_before_any_network_call(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = DownloadGameAssetTool(data_dir=tmp_path)
    with patch("sovereign_agent.tools.download_game_asset.httpx.AsyncClient") as m:
        result = await tool.execute(
            tool.Args(project_slug="alpha", url="https://kenney.nl/x.wav",
                     relative_path="a.wav", license_id="CC-BY-NC"),
            trace_id="t1",
        )
        m.assert_not_called()  # refused before ever touching the network
    assert not result.ok
    assert "license_not_allowed" in result.error


@pytest.mark.asyncio
async def test_cc_by_without_attribution_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = DownloadGameAssetTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", url="https://kenney.nl/x.wav",
                 relative_path="a.wav", license_id="CC-BY", attribution=""),
        trace_id="t1",
    )
    assert not result.ok
    assert "missing_attribution" in result.error


@pytest.mark.asyncio
async def test_over_budget_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    with patch("sovereign_agent.tools.download_game_asset.game_workspace_dir",
              return_value=workspace), \
         patch("sovereign_agent.tools.download_game_asset.game_assets.check_workspace_budget") as cb:
        from sovereign_agent.game_assets import BudgetStatus
        cb.return_value = BudgetStatus(used_bytes=600_000_000, budget_bytes=500_000_000)
        tool = DownloadGameAssetTool(data_dir=tmp_path)
        result = await tool.execute(
            tool.Args(project_slug="alpha", url="https://kenney.nl/x.wav",
                     relative_path="a.wav", license_id="CC0"),
            trace_id="t1",
        )
    assert not result.ok
    assert "over_budget" in result.error


@pytest.mark.asyncio
async def test_successful_download_writes_binary_and_manifest(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    content = b"RIFF\x00\x00\x00\x00WAVEfmt "
    with patch("sovereign_agent.tools.download_game_asset.game_workspace_dir",
              return_value=workspace), \
         patch("sovereign_agent.tools.download_game_asset.check_write_path",
              side_effect=lambda p, mode: p), \
         patch("sovereign_agent.tools.download_game_asset.httpx.AsyncClient",
              return_value=_fake_client(content=content)):
        tool = DownloadGameAssetTool(data_dir=tmp_path)
        result = await tool.execute(
            tool.Args(project_slug="alpha", url="https://kenney.nl/jump.wav",
                     relative_path="audio/jump.wav", license_id="CC0"),
            trace_id="t1",
        )
    assert result.ok
    saved = workspace / "assets" / "audio" / "jump.wav"
    assert saved.is_file()
    assert saved.read_bytes() == content
    manifest = workspace / "ASSET_LICENSES.md"
    assert manifest.is_file()
    assert "jump.wav" in manifest.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_too_large_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    big = b"x" * (21 * 1024 * 1024)
    with patch("sovereign_agent.tools.download_game_asset.game_workspace_dir",
              return_value=workspace), \
         patch("sovereign_agent.tools.download_game_asset.check_write_path",
              side_effect=lambda p, mode: p), \
         patch("sovereign_agent.tools.download_game_asset.httpx.AsyncClient",
              return_value=_fake_client(content=big)):
        tool = DownloadGameAssetTool(data_dir=tmp_path)
        result = await tool.execute(
            tool.Args(project_slug="alpha", url="https://kenney.nl/huge.wav",
                     relative_path="audio/huge.wav", license_id="CC0"),
            trace_id="t1",
        )
    assert not result.ok
    assert "too_large" in result.error
    assert not (workspace / "assets" / "audio" / "huge.wav").exists()
