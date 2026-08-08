"""Test-only path shim via the shared helper (scripts/lib/aria_conftest),
plus per-test SETTINGS isolation (staged-only — the live suite has its own
autouse isolated_paths): two memory-wing tasks write through SETTINGS
(thread chunks, atoms.db), so staged runs must never touch real data."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent,
             subpkgs=("proving_ground",))


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
