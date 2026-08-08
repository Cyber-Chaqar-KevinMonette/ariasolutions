"""Test-only path shim via the shared helper (scripts/lib/aria_conftest).

`workflow` isn't in aria_conftest's default subpackage list, so it's passed explicitly —
this payload adds a new file to the existing live `workflow/` package, not a new top-level one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent, subpkgs=("workflow",))
