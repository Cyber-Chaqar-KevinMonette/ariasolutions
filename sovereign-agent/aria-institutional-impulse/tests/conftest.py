"""Pre-apply conftest: inject staging payload into sovereign_agent.tools namespace.

When running M66 tests before apply_institutional_impulse.sh is run, the payload
modules don't exist in src/ yet. This conftest makes them importable from the
staging payload path so tests can validate the code before it's applied.

Once this module IS applied to live, the payload copy can drift stale (e.g.
if the real src/ file gets a follow-up fix the staged payload never
received) — injecting it unconditionally would then shadow the correct,
already-live module with an outdated one. Fixed: try the REAL import
first; only fall back to shadow-injecting the staged payload if the real
module genuinely isn't importable yet (the true pre-apply case).
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_PAYLOAD_SRC = Path(__file__).parent.parent / "payload" / "src"
_TOOLS_DIR = _PAYLOAD_SRC / "sovereign_agent" / "tools"


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


if _TOOLS_DIR.exists():
    for _p in sorted(_TOOLS_DIR.glob("*.py")):
        if _p.stem != "__init__":
            _inject_module(f"sovereign_agent.tools.{_p.stem}", _p)
