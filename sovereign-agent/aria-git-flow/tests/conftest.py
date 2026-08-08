"""Test-only path shim via the shared helper (scripts/lib/aria_conftest).

The scratch_repo fixture lives in test_git_flow_live.py itself (not
here) — it needs to travel with the file when promoted to live tests/,
where this staged-only conftest.py is never copied.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent)
