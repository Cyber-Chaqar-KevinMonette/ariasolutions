"""Test-only path shim via the shared helper (scripts/lib/aria_conftest)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

_MODULE_ROOT = Path(__file__).parent.parent
# extend_paths() appends the payload's sovereign_agent/ dir to
# sovereign_agent.__path__ — fine while reaction_roles/ only exists in the
# payload, but this module is now ALSO applied and live (2026-08-04): live
# src comes first in that list, so `import sovereign_agent.reaction_roles`
# (reaction_roles isn't in extend_paths()'s default subpkg list, so nothing
# has imported it yet at this point) would resolve the LIVE package first,
# never seeing payload edits like validate_panel_options. Promote the
# payload dir to the front and evict any stale cache entry — same fix as
# aria-game-bridge/tests/conftest.py needed once IT went live.
extend_paths(_MODULE_ROOT)

import sovereign_agent  # noqa: E402

_payload_root = str(_MODULE_ROOT / "payload" / "src" / "sovereign_agent")
if _payload_root in sovereign_agent.__path__:
    sovereign_agent.__path__.remove(_payload_root)
    sovereign_agent.__path__.insert(0, _payload_root)

sys.modules.pop("sovereign_agent.reaction_roles", None)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Staged-module counterpart to tests/conftest.py's isolated_paths.

    Once applied, this module's tests live under tests/ and inherit the
    real isolated_paths autouse fixture there for free. Pre-apply, this
    module's own aria-reaction-roles/tests/ tree is a SIBLING directory,
    not a subdirectory of tests/ — pytest's conftest resolution never
    reaches the root fixture for tests collected from here. Without this,
    reaction_roles.py's emit_event() call would write into the real
    production events.jsonl on every staged test run, not a tmp dir.
    Same technique as the root fixture: mutate SETTINGS.paths in place
    (frozen dataclass, object.__setattr__ bypasses it) so every module
    that already imported SETTINGS keeps working with the tmp paths.
    """
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config" / "sovereign-agent"
    data_dir = tmp_path / "data" / "sovereign-agent"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()

    original_paths = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield
    finally:
        object.__setattr__(SETTINGS, "paths", original_paths)
