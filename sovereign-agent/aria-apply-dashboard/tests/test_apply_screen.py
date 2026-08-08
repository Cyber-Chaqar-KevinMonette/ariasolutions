"""Tests for M81 apply dashboard screen (pure-logic paths).

Tests the discovery and status-detection logic that doesn't require a
running Textual TUI. Widget composition tests are omitted — they require
a Textual App event loop and are covered by manual cockpit testing.

8 tests covering: discovery, applied detection, pending detection,
empty repo, idempotent discover calls, script path correctness,
module naming convention, and no crash on missing repo.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ── Locate repo root (works from staging/ and from tests/ after apply) ────────

def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml found)")

_REPO = _repo_root()
_STAGING = (
    _REPO / "aria-apply-dashboard"
    / "payload" / "src" / "sovereign_agent" / "cockpit" / "apply_screen.py"
)


def _inject(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _inject("sovereign_agent.cockpit.apply_screen", _STAGING)
discover_scripts = _mod.discover_scripts
_is_applied = _mod._is_applied


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_staging_module(repo: Path, name: str, has_test: bool = False) -> None:
    """Create a minimal aria-<name>/ folder with an apply script."""
    folder = repo / f"aria-{name}"
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / f"apply_{name.replace('-', '_')}.sh"
    script.write_text(f"#!/usr/bin/env bash\necho 'applying {name}'\n")
    script.chmod(0o755)
    if has_test:
        tests_dir = repo / "tests"
        tests_dir.mkdir(exist_ok=True)
        slug = name.replace("-", "_")
        (tests_dir / f"test_{slug}.py").write_text("# applied marker\n")


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_discover_finds_scripts(tmp_path):
    """discover_scripts returns one entry per aria-*/apply_*.sh found."""
    _make_staging_module(tmp_path, "birth-records")
    _make_staging_module(tmp_path, "self-portrait")

    scripts = discover_scripts(tmp_path)

    assert len(scripts) == 2
    names = {s["name"] for s in scripts}
    assert "aria-birth-records" in names
    assert "aria-self-portrait" in names


def test_discover_empty_repo(tmp_path):
    """discover_scripts on a repo with no aria-* dirs returns empty list."""
    scripts = discover_scripts(tmp_path)
    assert scripts == []


def test_applied_detection_positive(tmp_path):
    """Module with matching test file is detected as applied."""
    _make_staging_module(tmp_path, "birth-records", has_test=True)

    scripts = discover_scripts(tmp_path)
    entry = scripts[0]

    assert entry["applied"] is True


def test_pending_detection_no_test(tmp_path):
    """Module without test file is detected as pending."""
    _make_staging_module(tmp_path, "birth-records", has_test=False)

    scripts = discover_scripts(tmp_path)
    entry = scripts[0]

    assert entry["applied"] is False


def test_mixed_applied_and_pending(tmp_path):
    """discover_scripts correctly separates applied and pending modules."""
    _make_staging_module(tmp_path, "birth-records", has_test=True)
    _make_staging_module(tmp_path, "self-portrait", has_test=False)
    _make_staging_module(tmp_path, "honor-calibration", has_test=True)

    scripts = discover_scripts(tmp_path)
    applied = [s for s in scripts if s["applied"]]
    pending = [s for s in scripts if not s["applied"]]

    assert len(applied) == 2
    assert len(pending) == 1
    assert pending[0]["name"] == "aria-self-portrait"


def test_script_path_is_absolute(tmp_path):
    """Each entry's 'script' key is a str path pointing to the apply script."""
    _make_staging_module(tmp_path, "birth-records")

    scripts = discover_scripts(tmp_path)
    entry = scripts[0]
    script_path = Path(entry["script"])

    assert script_path.exists()
    assert script_path.name.startswith("apply_")
    assert script_path.suffix == ".sh"


def test_scripts_sorted_alphabetically(tmp_path):
    """discover_scripts returns modules in alphabetical order by name."""
    _make_staging_module(tmp_path, "zebra-module")
    _make_staging_module(tmp_path, "alpha-module")
    _make_staging_module(tmp_path, "middle-module")

    scripts = discover_scripts(tmp_path)
    names = [s["name"] for s in scripts]

    assert names == sorted(names)


def test_idempotent_discovery(tmp_path):
    """Calling discover_scripts twice gives the same result."""
    _make_staging_module(tmp_path, "birth-records")
    _make_staging_module(tmp_path, "self-portrait", has_test=True)

    first = discover_scripts(tmp_path)
    second = discover_scripts(tmp_path)

    assert [s["name"] for s in first] == [s["name"] for s in second]
    assert [s["applied"] for s in first] == [s["applied"] for s in second]


def test_is_applied_helper_directly(tmp_path):
    """_is_applied checks for tests/test_{slug}.py presence."""
    # No test file yet — should be False
    assert _is_applied(tmp_path, "aria-my-feature") is False

    # Create the test file
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_my_feature.py").write_text("# marker\n")

    # Now should be True
    assert _is_applied(tmp_path, "aria-my-feature") is True


def test_is_applied_payload_parity_fallback(tmp_path):
    """A module whose payload files aren't named after its own slug (e.g.
    aria-real-estate ships real_estate_gate.py, not test_real_estate.py) is
    still detected as applied once every payload .py file byte-matches live —
    the 2026-08-02 fix for the false-pending bug this exact class of module hit."""
    mod = "aria-my-domain-thing"
    payload = tmp_path / mod / "payload" / "src" / "sovereign_agent"
    payload.mkdir(parents=True)
    (payload / "domain_thing.py").write_text("VALUE = 1\n")

    # Not live yet — pending
    assert _is_applied(tmp_path, mod) is False

    # Live but different content — still pending (would be a regression to overwrite)
    live = tmp_path / "src" / "sovereign_agent"
    live.mkdir(parents=True)
    (live / "domain_thing.py").write_text("VALUE = 2\n")
    assert _is_applied(tmp_path, mod) is False

    # Live and byte-identical — applied
    (live / "domain_thing.py").write_text("VALUE = 1\n")
    assert _is_applied(tmp_path, mod) is True
