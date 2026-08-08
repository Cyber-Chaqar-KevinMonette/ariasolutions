"""Test path shim. Resilience layer scans reach into nonclassical-supreme + tribunal + foresight."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

_repo = Path(__file__).parents[2]
extend_paths(Path(__file__).parent.parent,
             extra_roots=(_repo / "aria-nonclassical-supreme", _repo / "aria-tribunal", _repo / "aria-foresight"))
