"""Tests for the v0.2.5 CLI surface.

Coverage:
  - --version, --help on top-level and every subcommand
  - --json output shape for read commands
  - exit codes for every guarded path (not-init, halted, locked, etc.)
  - plan creates a continuation; continuations list/show/delete round-trip
  - dry-run paths don't need ollama
  - existing v0.2.4 commands still work
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sovereign_agent.cli import ExitCode, app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── Top-level basics ───────────────────────────────────────────────────────


def test_version_flag_prints_and_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == ExitCode.OK
    assert "sovereign-agent" in result.stdout


def test_help_works(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == ExitCode.OK
    # All major command groups should appear in help.
    for cmd in ("init", "doctor", "run", "busy", "plan", "continue",
                "continuations", "backlog", "approvals", "halt", "events"):
        assert cmd in result.stdout, f"command {cmd!r} missing from help"


@pytest.mark.parametrize("cmd", [
    ["init", "--help"],
    ["doctor", "--help"],
    ["config", "--help"],
    ["run", "--help"],
    ["busy", "--help"],
    ["until", "--help"],
    ["plan", "--help"],
    ["continue", "--help"],
    ["continuations", "--help"],
    ["continuations", "list", "--help"],
    ["continuations", "show", "--help"],
    ["continuations", "delete", "--help"],
    ["backlog", "--help"],
    ["backlog", "add", "--help"],
    ["backlog", "list", "--help"],
    ["backlog", "show", "--help"],
    ["backlog", "remove", "--help"],
    ["backlog", "requeue", "--help"],
    ["backlog", "priority", "--help"],
    ["backlog", "clear", "--help"],
    ["approvals", "--help"],
    ["approve", "--help"],
    ["deny", "--help"],
    ["halt", "--help"],
    ["disarm", "--help"],
    ["tail", "--help"],
    ["seal", "--help"],
    ["verify", "--help"],
    ["events", "--help"],
    ["lessons", "--help"],
])
def test_help_for_every_command(runner: CliRunner, cmd: list[str]) -> None:
    result = runner.invoke(app, cmd)
    assert result.exit_code == ExitCode.OK, \
        f"--help failed for {cmd}: stderr={result.stderr}"


# ─── Init / config / doctor (don't need ollama) ─────────────────────────────


def test_init_creates_dirs_and_secret(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"],
    )
    assert result.exit_code == ExitCode.OK, result.stderr
    assert (cfg / "secret.key").exists()
    assert (data / "sandbox").is_dir()
    assert (data / "events").is_dir()
    assert (data / "continuations").is_dir()


def test_init_json_output(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json", "init"],
    )
    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "continuations" in payload


def test_config_show_json(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json", "config"],
    )
    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    assert payload["paths"]["config_dir"] == str(cfg)
    assert payload["paths"]["data_dir"] == str(data)
    assert "models" in payload
    assert "ollama_host" in payload


def test_doctor_runs_without_init(runner: CliRunner, tmp_path: Path) -> None:
    """Doctor is read-only; should never need init."""
    result = runner.invoke(
        app, ["--config-dir", str(tmp_path / "cfg"), "--data-dir", str(tmp_path / "data"),
              "--json", "doctor"],
    )
    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    assert "checks" in payload
    assert payload["fail_count"] >= 0


# ─── Pre-flight refusals ────────────────────────────────────────────────────


def test_run_refuses_when_not_initialized(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "run", "test goal"],
    )
    assert result.exit_code == ExitCode.NOT_INITIALIZED


def test_run_refuses_when_halted(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    (cfg / "HALT").write_text("test halt\n")
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "run", "test goal"],
    )
    assert result.exit_code == ExitCode.HALTED


def test_continue_refuses_when_not_initialized(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "continue", "cont-anything"],
    )
    assert result.exit_code == ExitCode.NOT_INITIALIZED


# ─── Run dry-run (avoids ollama entirely) ───────────────────────────────────


def test_run_dry_run(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "--json", "run", "test goal", "--dry-run"],
    )
    assert result.exit_code == ExitCode.OK, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["mode"] == "oneshot"
    assert "tier_ceiling" in payload
    assert "available_tools" in payload
    assert isinstance(payload["available_tools"], list)


def test_run_dry_run_busy_mode_excludes_tier2_3_tools(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "--json", "run", "test", "--mode", "busy", "--dry-run"],
    )
    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    assert payload["tier_ceiling"] == 1


# ─── Plan / continue / continuations workflow ───────────────────────────────


def test_plan_lists_planners(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json", "plan"],
    )
    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    names = {p["name"] for p in payload["planners"]}
    assert "inventory" in names
    assert "read-files" in names


def test_plan_unknown_planner_returns_usage_error(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "plan", "nonexistent-planner"],
    )
    assert result.exit_code == ExitCode.USAGE


def test_plan_dry_run_inventory(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.md").write_text("alpha")
    (target / "b.md").write_text("beta")
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "plan", "inventory", "--root", str(target),
              "--output", str(tmp_path / "INVENTORY.txt"),
              "--pattern", "*.md", "--dry-run"],
    )
    assert result.exit_code == ExitCode.OK, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["step_count"] == 2


def test_plan_creates_continuation_then_show_delete(runner: CliRunner, tmp_path: Path) -> None:
    """Full plan → list → show → delete round-trip via the CLI."""
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])

    target = tmp_path / "target"
    target.mkdir()
    (target / "x.md").write_text("x"); (target / "y.md").write_text("y")
    out = tmp_path / "OUT.txt"

    # Plan — creates a continuation.
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "plan", "inventory", "--root", str(target),
              "--output", str(out), "--pattern", "*.md"],
    )
    assert r.exit_code == ExitCode.OK, r.stderr
    plan_payload = json.loads(r.stdout)
    task_id = plan_payload["task_id"]
    assert plan_payload["step_count"] == 2

    # List — should include the new continuation.
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "continuations", "list"],
    )
    assert r.exit_code == ExitCode.OK
    listed = json.loads(r.stdout)["continuations"]
    assert any(c["task_id"] == task_id for c in listed)

    # Show — full detail.
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "continuations", "show", task_id],
    )
    assert r.exit_code == ExitCode.OK
    detail = json.loads(r.stdout)
    assert detail["task_id"] == task_id
    assert len(detail["steps"]) == 2

    # Delete.
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "continuations", "delete", task_id],
    )
    assert r.exit_code == ExitCode.OK
    deleted = json.loads(r.stdout)
    assert deleted["deleted"] is True

    # Show after delete — usage error.
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "continuations", "show", task_id],
    )
    assert r.exit_code == ExitCode.USAGE


def test_continuations_show_unknown_id_is_usage_error(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    result = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "continuations", "show", "cont-nope"],
    )
    assert result.exit_code == ExitCode.USAGE


# ─── Backlog round-trip ─────────────────────────────────────────────────────


def test_backlog_add_list_show_priority_requeue_remove(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])

    # Add
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "add", "do something useful"],
    )
    assert r.exit_code == ExitCode.OK
    task_id = json.loads(r.stdout)["id"]

    # List
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "list"],
    )
    assert r.exit_code == ExitCode.OK
    tasks = json.loads(r.stdout)["tasks"]
    assert any(t["id"] == task_id for t in tasks)

    # Show
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "show", task_id],
    )
    assert r.exit_code == ExitCode.OK
    assert json.loads(r.stdout)["id"] == task_id

    # Priority change
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "priority", task_id, "high"],
    )
    assert r.exit_code == ExitCode.OK
    assert json.loads(r.stdout)["priority"] == "high"

    # Invalid priority
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "backlog", "priority", task_id, "garbage"],
    )
    assert r.exit_code == ExitCode.USAGE

    # Requeue
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "requeue", task_id],
    )
    assert r.exit_code == ExitCode.OK

    # Remove
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "remove", task_id],
    )
    assert r.exit_code == ExitCode.OK
    assert json.loads(r.stdout)["ok"] is True


def test_backlog_clear_with_yes_flag(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "backlog", "add", "task A"],
    )
    # Manually mark it done by writing the YAML file
    import yaml
    bl = cfg / "backlog.yaml"
    data_yaml = yaml.safe_load(bl.read_text())
    data_yaml["tasks"][0]["status"] = "done"
    bl.write_text(yaml.safe_dump(data_yaml))

    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "backlog", "clear", "--status", "done", "--yes"],
    )
    assert r.exit_code == ExitCode.OK
    assert json.loads(r.stdout)["removed"] == 1


# ─── Halt / disarm / approvals ──────────────────────────────────────────────


def test_halt_then_disarm(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json",
              "halt", "--reason", "test"],
    )
    assert r.exit_code == ExitCode.OK
    assert (cfg / "HALT").exists()

    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json", "disarm"],
    )
    assert r.exit_code == ExitCode.OK
    assert not (cfg / "HALT").exists()


def test_approvals_empty(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data), "--json", "approvals"],
    )
    assert r.exit_code == ExitCode.OK
    assert json.loads(r.stdout)["pending"] == []


def test_approve_unknown_event_id(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "approve", "01J9NEVER", "--yes"],
    )
    assert r.exit_code == ExitCode.APPROVAL_NOT_FOUND


# ─── Verify uses correct exit codes ─────────────────────────────────────────


def test_verify_invalid_date_returns_usage_error(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(
        app, ["--config-dir", str(cfg), "--data-dir", str(data),
              "verify", "not-a-date"],
    )
    assert r.exit_code == ExitCode.USAGE
