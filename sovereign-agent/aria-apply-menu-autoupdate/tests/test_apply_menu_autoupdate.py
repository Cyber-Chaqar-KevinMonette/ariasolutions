"""Tests for M85: Apply Dashboard auto-discovery improvements.

Covers _extract_script_info(), updated _is_applied(), and discover_scripts()
returning label + description for modules not in _CATALOG.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import importlib.util
import sys

import pytest

# ── Import helpers ────────────────────────────────────────────────────────────

def _load_apply_screen():
    """Load apply_screen from the live src/ tree, bypassing sys.modules cache.

    Uses a unique module name so that test_apply_screen.py's _inject of the
    staging version doesn't collide with the live version we need here.
    """
    _mod_name = "_apply_screen_live_m85"
    if _mod_name in sys.modules:
        return sys.modules[_mod_name]
    here = Path(__file__).resolve()
    # Walk up to find repo root (has pyproject.toml)
    root = here.parent
    for _ in range(6):
        if (root / "pyproject.toml").exists():
            break
        root = root.parent
    live = root / "src" / "sovereign_agent" / "cockpit" / "apply_screen.py"
    spec = importlib.util.spec_from_file_location(_mod_name, live)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── _extract_script_info ──────────────────────────────────────────────────────

def test_extract_stage_pattern(tmp_path):
    """Stage M99: pattern → (M99 · Title, Title)."""
    m = _load_apply_screen()
    script = tmp_path / "apply_foo.sh"
    script.write_text("#!/usr/bin/env bash\n# apply_foo.sh — Stage M99: Widget layer\n")
    label, desc = m._extract_script_info(script)
    assert label == "M99 · Widget layer"
    assert desc == "Widget layer"


def test_extract_apply_pattern(tmp_path):
    """Apply M75: pattern → (M75 · Title, Title)."""
    m = _load_apply_screen()
    script = tmp_path / "apply_bar.sh"
    script.write_text("#!/usr/bin/env bash\n# apply_bar.sh — Apply M75: founding atoms\n")
    label, desc = m._extract_script_info(script)
    assert label == "M75 · founding atoms"
    assert desc == "founding atoms"


def test_extract_no_m_number(tmp_path):
    """Header without M-number → full description as both label and desc."""
    m = _load_apply_screen()
    script = tmp_path / "apply_x.sh"
    script.write_text("#!/usr/bin/env bash\n# apply_x.sh — Some plain description here\n")
    label, desc = m._extract_script_info(script)
    assert label == "Some plain description here"
    assert desc == "Some plain description here"


def test_extract_fallback_on_no_comment(tmp_path):
    """Script with no header comment → folder name fallback."""
    m = _load_apply_screen()
    # Put the script inside a named folder
    folder = tmp_path / "aria-special-module"
    folder.mkdir()
    script = folder / "apply_special_module.sh"
    script.write_text("#!/usr/bin/env bash\nset -euo pipefail\n")
    label, desc = m._extract_script_info(script)
    assert label == "aria-special-module"
    assert desc == ""


def test_extract_multiline_description_uses_first(tmp_path):
    """Only the first non-shebang comment line is used."""
    m = _load_apply_screen()
    script = tmp_path / "apply_m.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "# apply_m.sh — Stage M88: First line title\n"
        "# Second line description ignored\n"
    )
    label, desc = m._extract_script_info(script)
    assert "M88" in label
    assert "First line title" in label


# ── _is_applied ───────────────────────────────────────────────────────────────

def test_is_applied_via_backups_dir(tmp_path):
    """backups/ directory in staging folder → applied=True."""
    m = _load_apply_screen()
    staging = tmp_path / "aria-foo"
    staging.mkdir()
    (staging / "backups").mkdir()
    assert m._is_applied(tmp_path, "aria-foo") is True


def test_is_applied_via_test_file(tmp_path):
    """tests/test_foo.py in repo root → applied=True even without backups/."""
    m = _load_apply_screen()
    (tmp_path / "aria-foo").mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("# test")
    assert m._is_applied(tmp_path, "aria-foo") is True


def test_is_applied_neither_heuristic(tmp_path):
    """No backups/ and no test file → applied=False."""
    m = _load_apply_screen()
    (tmp_path / "aria-bar").mkdir()
    assert m._is_applied(tmp_path, "aria-bar") is False


def test_is_applied_backups_wins_over_no_test(tmp_path):
    """backups/ present but no test file → still True (backups wins)."""
    m = _load_apply_screen()
    staging = tmp_path / "aria-baz"
    staging.mkdir()
    (staging / "backups").mkdir()
    # No tests/ dir at all
    assert m._is_applied(tmp_path, "aria-baz") is True


# ── discover_scripts ──────────────────────────────────────────────────────────

def test_discover_includes_label_and_description(tmp_path):
    """discover_scripts() entries include label and description keys."""
    m = _load_apply_screen()
    folder = tmp_path / "aria-test-mod"
    folder.mkdir()
    script = folder / "apply_test_mod.sh"
    script.write_text("#!/usr/bin/env bash\n# apply_test_mod.sh — Stage M99: Test module\n")

    results = m.discover_scripts(tmp_path)
    assert len(results) == 1
    entry = results[0]
    assert "label" in entry
    assert "description" in entry
    assert "M99" in entry["label"]
    assert "Test module" in entry["description"]


def test_discover_applied_flag_via_backups(tmp_path):
    """discover_scripts() correctly marks module as applied via backups/ dir."""
    m = _load_apply_screen()
    folder = tmp_path / "aria-live-mod"
    folder.mkdir()
    (folder / "backups").mkdir()
    script = folder / "apply_live_mod.sh"
    script.write_text("#!/usr/bin/env bash\n# apply_live_mod.sh — Stage M11: Live module\n")

    results = m.discover_scripts(tmp_path)
    assert results[0]["applied"] is True


def test_discover_sorted_alphabetically(tmp_path):
    """discover_scripts() returns entries sorted alphabetically by folder name."""
    m = _load_apply_screen()
    for name in ["aria-zzz", "aria-aaa", "aria-mmm"]:
        folder = tmp_path / name
        folder.mkdir()
        script = folder / f"apply_{name.removeprefix('aria-')}.sh"
        script.write_text(f"#!/usr/bin/env bash\n# {script.name} — Stage M1: {name}\n")

    results = m.discover_scripts(tmp_path)
    names = [r["name"] for r in results]
    assert names == sorted(names)
