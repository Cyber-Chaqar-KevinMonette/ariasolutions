"""Test path shim via the shared helper. Frugality also needs aria_lm (from aria-own-mind) for BitNet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

_repo = Path(__file__).parents[2]
extend_paths(Path(__file__).parent.parent, extra_roots=(_repo / "aria-own-mind",))
