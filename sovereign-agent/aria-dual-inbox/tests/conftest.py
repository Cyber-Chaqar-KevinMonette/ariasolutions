"""aria-dual-inbox/tests/conftest.py — pre-apply test shim.

`workflow/requests.py` already exists live (it predates this module — see
aria-inbox-context) but WITHOUT the new `direction` field/methods this
module's payload adds. Appending the payload path to `sovereign_agent.
__path__` (the usual extend_paths trick) does NOT help for an
already-existing submodule: Python resolves it from whichever `__path__`
entry comes first, and the live src entry always wins. So — same approach
as aria-safe-interval-stop's conftest — we pre-populate
`sys.modules["sovereign_agent.workflow.requests"]` with the PAYLOAD's copy
before anything else has a chance to import the live one. Safe because it
runs once, before first use, in a fresh pytest process dedicated to this
module's own isolated test run. Never copied to live tests/.

`inbox_tools.py` (new, no live conflict) resolves fine via the normal
extend_paths append — "tools" is already in aria_conftest's default subpkgs.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MODULE_ROOT = _HERE.parent
_PAYLOAD_REQUESTS = (
    _MODULE_ROOT / "payload" / "src" / "sovereign_agent" / "workflow" / "requests.py"
)

if "sovereign_agent.workflow.requests" not in sys.modules:
    import sovereign_agent  # noqa: F401 — establishes the base package/__path__
    import sovereign_agent.workflow  # noqa: F401 — establishes the parent package

    _spec = importlib.util.spec_from_file_location(
        "sovereign_agent.workflow.requests", _PAYLOAD_REQUESTS
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["sovereign_agent.workflow.requests"] = _module
    _spec.loader.exec_module(_module)
    sys.modules["sovereign_agent.workflow"].requests = _module

sys.path.insert(0, str(_MODULE_ROOT.parent / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(_MODULE_ROOT)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path):
    """Redirect SETTINGS.paths into a tmp dir for every test — RequestStore
    opens a real atoms.db via ErebloStore, and this test file must never
    touch a real install's data. Mirrors tests/conftest.py's own fixture."""
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
