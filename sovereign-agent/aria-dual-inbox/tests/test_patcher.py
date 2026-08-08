"""Text-transform tests for aria-dual-inbox's patcher.py — proves the
cli.py/app.py/tools __init__ patches apply cleanly against the CURRENT live
files, are idempotent, and the patched files still compile."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher import MARK, PatchError, patch_app_inbox, patch_cli, patch_tools_init  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PY = REPO_ROOT / "src" / "sovereign_agent" / "cli.py"
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"
TOOLS_INIT_PY = REPO_ROOT / "src" / "sovereign_agent" / "tools" / "__init__.py"

STAGING = Path(__file__).resolve().parents[1]
NEW_CLI_BLOCK = (STAGING / "payload" / "cli_requests_block.py").read_text(encoding="utf-8")
NEW_APP_BLOCK = (STAGING / "payload" / "app_inbox_pane_block.py").read_text(encoding="utf-8")


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(text)
        tmp_name = fh.name
    py_compile.compile(tmp_name, doraise=True)


# ─── cli.py ─────────────────────────────────────────────────────────────────


def _pre_apply_backup(name: str) -> str:
    """The genuine pre-apply snapshot (written by apply_dual_inbox.sh before
    patching) — the only reliable way to test "does patch_X raise on a
    broken anchor" now that live already has MARK and the patcher's own
    early-exit (`if MARK in text: return text, False`) would otherwise
    short-circuit before ever reaching the anchor search."""
    backups = sorted((STAGING / "backups").glob("*/" + name))
    assert backups, f"no pre-apply backup found for {name!r}"
    return backups[0].read_text(encoding="utf-8")


def test_patch_cli_applies_and_is_idempotent():
    text = CLI_PY.read_text(encoding="utf-8")
    once, _ = patch_cli(text, NEW_CLI_BLOCK)  # changed may be False if already applied
    assert MARK in once
    assert "requests_tell_cmd" in once
    assert '"--direction"' in once
    twice, changed_again = patch_cli(once, NEW_CLI_BLOCK)
    assert not changed_again
    assert twice == once


def test_patched_cli_compiles():
    text = CLI_PY.read_text(encoding="utf-8")
    patched, _ = patch_cli(text, NEW_CLI_BLOCK)
    _compiles(patched)


def test_patch_cli_raises_loud_on_moved_start_anchor():
    pre_apply = _pre_apply_backup("cli.py.bak")
    broken = pre_apply.replace(
        "requests_app = typer.Typer(\n", "requests_app = typer.Typer(  # moved\n"
    )
    with pytest.raises(PatchError):
        patch_cli(broken, NEW_CLI_BLOCK)


# ─── cockpit/app.py ─────────────────────────────────────────────────────────


def test_patch_app_inbox_applies_and_is_idempotent():
    text = APP_PY.read_text(encoding="utf-8")
    once, _ = patch_app_inbox(text, NEW_APP_BLOCK)  # changed may be False if already applied
    assert MARK in once
    assert "to_aria_items" in once
    assert "def _refresh_memory_pane" in once  # untouched, still present right after
    twice, changed_again = patch_app_inbox(once, NEW_APP_BLOCK)
    assert not changed_again
    assert twice == once


def test_patched_app_compiles():
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app_inbox(text, NEW_APP_BLOCK)
    _compiles(patched)


def test_patch_app_inbox_leaves_everything_else_byte_identical():
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app_inbox(text, NEW_APP_BLOCK)
    before_method = text.split("    def _refresh_inbox_pane(self) -> None:\n")[0]
    after_method = text.split("    def _refresh_memory_pane(self) -> None:\n", 1)[1]
    assert patched.startswith(before_method)
    assert patched.endswith(after_method)


# ─── tools/__init__.py ──────────────────────────────────────────────────────


def test_patch_tools_init_applies_and_is_idempotent():
    text = TOOLS_INIT_PY.read_text(encoding="utf-8")
    once, _ = patch_tools_init(text)  # changed may be False if already applied
    assert MARK in once
    assert "from .inbox_tools import SendToHumanTool, ReadInboxTool" in once
    assert '"SendToHumanTool"' in once
    assert '"ReadInboxTool"' in once
    twice, changed_again = patch_tools_init(once)
    assert not changed_again
    assert twice == once


def test_patched_tools_init_compiles():
    text = TOOLS_INIT_PY.read_text(encoding="utf-8")
    patched, _ = patch_tools_init(text)
    _compiles(patched)
