"""Pre-apply conftest: inject staging payloads into sovereign_agent.tools namespace.

When running M67 tests before the apply scripts are run, the payload modules
don't exist in src/ yet. This conftest makes them importable from the staging
payload paths so tests can validate the code before it's applied.

M67 integration test also imports impulse_tools (M66), so both payloads are
injected here.

Once these modules ARE applied to live (both are, confirmed), a staged
payload copy can drift stale relative to the real, already-live module —
injecting it unconditionally would shadow the correct module with an
outdated one. Fixed: try the REAL import first; only fall back to
shadow-injecting the staged payload if the real module genuinely isn't
importable yet (the true pre-apply case).
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent.parent

_PAYLOAD_DIRS = [
    _REPO / "aria-institutional-impulse" / "payload" / "src" / "sovereign_agent" / "tools",
    _REPO / "aria-proof-crown" / "payload" / "src" / "sovereign_agent" / "tools",
]


def _inject_module(mod_name: str, file_path: Path) -> None:
    if mod_name in sys.modules:
        return
    try:
        importlib.import_module(mod_name)
        return  # already live and importable — never shadow it with a stale payload copy
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        del sys.modules[mod_name]
        raise


for _tools_dir in _PAYLOAD_DIRS:
    if _tools_dir.exists():
        for _p in sorted(_tools_dir.glob("*.py")):
            if _p.stem != "__init__":
                _inject_module(f"sovereign_agent.tools.{_p.stem}", _p)
