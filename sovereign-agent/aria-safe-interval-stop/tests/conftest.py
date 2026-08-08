"""aria-safe-interval-stop/tests/conftest.py — pre-apply test shim.

`work_interval.py` (new) does `from .modes import RunBudget, effective_wall_limit`.
`effective_wall_limit` and `RunBudget.safety_margin_seconds` only exist in this
module's STAGED payload copy of `modes.py` — live `src/`'s copy doesn't have
them yet. `modes.py` already exists live, so the usual `extend_paths` trick
(appending the payload path to `sovereign_agent.__path__`) does NOT help here:
Python resolves an already-existing submodule from whichever `__path__` entry
comes first, and the live src entry is always first (it's how the package was
found in the first place). So we pre-populate
`sys.modules["sovereign_agent.modes"]` with the PAYLOAD's copy before anything
else has a chance to import the live one.

This is safe and NOT the sys.modules-deletion anti-pattern fixed elsewhere
this session (see test_locator_events_fix.py's history): it runs once, before
first use, in a fresh pytest process dedicated to this module's own isolated
test run — it never deletes or replaces an already-established singleton
mid-session. This conftest.py is intentionally NOT copied to live tests/ by
this module's apply script; only the plain test_*.py file is promoted, and it
runs post-apply under the repo's real conftest.py with no shimming needed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MODULE_ROOT = _HERE.parent
_PAYLOAD_MODES = _MODULE_ROOT / "payload" / "src" / "sovereign_agent" / "modes.py"

if "sovereign_agent.modes" not in sys.modules:
    import sovereign_agent  # noqa: F401 — establishes the base package/__path__ first

    _spec = importlib.util.spec_from_file_location("sovereign_agent.modes", _PAYLOAD_MODES)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["sovereign_agent.modes"] = _module
    _spec.loader.exec_module(_module)

sys.path.insert(0, str(_MODULE_ROOT.parent / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(_MODULE_ROOT)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path):
    """Redirect SETTINGS.paths.config_dir into a tmp dir for every test in
    this module's own isolated run — interrupts.py reads/writes flag files
    under config_dir, and this test file must never touch a real install's
    ~/.config/sovereign-agent/. Mirrors the real tests/conftest.py's own
    isolated_paths fixture (object.__setattr__ on the frozen SETTINGS/Paths
    dataclasses, restored in `finally`) — this staged conftest is never
    copied to live tests/, so there's no duplication once applied."""
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()

    original_paths = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield
    finally:
        object.__setattr__(SETTINGS, "paths", original_paths)
