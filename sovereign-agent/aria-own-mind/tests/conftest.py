"""Test path shim via the shared helper (scripts/lib/aria_conftest) — resolves sovereign_agent.aria_lm."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent)
