"""Tests for game-studio-capabilities-d — godot_export (Tier 2, stays
above BUSY's ceiling on purpose — it writes a real build artifact)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
from sovereign_agent.tools.godot_export import GodotExportTool


def test_tool_registered_at_tier_2():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "godot_export" in _TIER_REGISTRY
    assert _TIER_REGISTRY["godot_export"].tier == 2


def test_not_reachable_under_busy_mode_ceiling():
    """Deliberate: export writes a real artifact, stays gated to
    interactive modes, unlike godot_check."""
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "godot_export" not in names


@pytest.mark.asyncio
async def test_export_unknown_preset_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    (workspace / "export_presets.cfg").write_text('[preset.0]\nname="Linux/X11"\n', encoding="utf-8")
    with patch("sovereign_agent.tools.godot_export.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_export.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotExportTool(data_dir=tmp_path)
        result = await tool.execute(
            tool.Args(project_slug="alpha", preset="Windows", output_relative_path="out.exe"),
            trace_id="t1",
        )
    assert not result.ok
    assert "unknown_preset" in result.error


@pytest.mark.asyncio
async def test_export_valid_preset_invokes_godot(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    (workspace / "export_presets.cfg").write_text('[preset.0]\nname="Linux/X11"\n', encoding="utf-8")
    fake = MagicMock(returncode=0, stdout="Exported.\n", stderr="")
    with patch("sovereign_agent.tools.godot_export.subprocess.run", return_value=fake) as m, \
         patch("sovereign_agent.tools.godot_export.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_export.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotExportTool(data_dir=tmp_path)
        result = await tool.execute(
            tool.Args(project_slug="alpha", preset="Linux/X11",
                     output_relative_path="builds/game.pck"),
            trace_id="t1",
        )
    assert result.ok
    argv = m.call_args.args[0]
    assert "--export-release" in argv and "Linux/X11" in argv


@pytest.mark.asyncio
async def test_export_timeout_is_adjustable_and_actually_used():  # timeout-hardening-d
    """Kevin, 2026-07-21: "adaptable timeouts... and longer timeouts."
    Was a hardcoded 120s with no way to ask for more; now a default with
    a raisable ceiling. Prove the requested value actually reaches
    subprocess.run, not just that the Args field accepts it."""
    save(GameProject(project_name="Alpha"), tmp_path := __import__("pathlib").Path("/tmp"))
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox-timeout-test")
    (workspace / "export_presets.cfg").write_text('[preset.0]\nname="Linux/X11"\n', encoding="utf-8")
    fake = MagicMock(returncode=0, stdout="Exported.\n", stderr="")
    with patch("sovereign_agent.tools.godot_export.subprocess.run", return_value=fake) as m, \
         patch("sovereign_agent.tools.godot_export.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_export.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotExportTool(data_dir=tmp_path)
        result = await tool.execute(
            tool.Args(project_slug="alpha", preset="Linux/X11",
                     output_relative_path="builds/game.pck", timeout=600),
            trace_id="t1",
        )
    assert result.ok
    assert m.call_args.kwargs["timeout"] == 600


def test_export_timeout_ceiling_is_raised_but_still_bounded():
    from sovereign_agent.tools.godot_export import GodotExportTool, _MAX_TIMEOUT

    assert _MAX_TIMEOUT > 120  # genuinely raised from the old hardcoded 120s
    try:
        GodotExportTool.Args(project_slug="a", preset="p", output_relative_path="o",
                             timeout=_MAX_TIMEOUT + 1)
        assert False, "expected a validation error over the ceiling"
    except Exception:
        pass
