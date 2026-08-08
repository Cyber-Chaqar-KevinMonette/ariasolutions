"""Test-only path shim via the shared helper (scripts/lib/aria_conftest).
I1 (aria-integrity-ledger) is already applied live, so
`sovereign_agent.integrity` already exists — this only needs to extend
that already-live package's __path__ with I2's own staged gate.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent, subpkgs=("integrity",))
