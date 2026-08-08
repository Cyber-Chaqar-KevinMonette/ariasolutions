"""Test-only path shim via the shared helper (scripts/lib/aria_conftest),
plus per-test SETTINGS isolation (staged-only — the live suite has its own
autouse isolated_paths). W1 (aria-wellbeing-ledger) is already applied
live, so `sovereign_agent.wellbeing` already exists — this only needs to
extend that already-live package's __path__ with W2's own staged gate.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent, subpkgs=("wellbeing",))


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config" / "sovereign-agent"
    data_dir = tmp_path / "data" / "sovereign-agent"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()
    original = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield
    finally:
        object.__setattr__(SETTINGS, "paths", original)
