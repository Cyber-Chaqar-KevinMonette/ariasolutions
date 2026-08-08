"""Test-only path shim via the shared helper (scripts/lib/aria_conftest).

Also grafts aria-path-sentinel's payload (Workstream D) since it isn't applied to
live src yet either, and the fan-out layer's tests exercise it directly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(
    Path(__file__).parent.parent,
    extra_roots=(Path(__file__).parents[2] / "aria-path-sentinel",),
)
