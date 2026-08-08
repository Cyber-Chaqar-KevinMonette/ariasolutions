"""Patch stewardship/__init__.py to register the 8 dormant sentinels."""
import sys

path = sys.argv[1]
src = open(path).read()

anchor = "from . import atoms_compact_sentinel as _atoms_compact_sentinel  # noqa: F401  # atoms-compact-sentinel-d"
addition = """
from . import watchdog_sentinel as _watchdog_sentinel              # noqa: F401  # M55-sentinel-crown-d
from . import conformance_sentinel as _conformance_sentinel        # noqa: F401  # M55-sentinel-crown-d
from . import defense_sentinel as _defense_sentinel                # noqa: F401  # M55-sentinel-crown-d
from . import memory_garden as _memory_garden                      # noqa: F401  # M55-sentinel-crown-d
from . import passive_watcher_sentinel as _passive_watcher         # noqa: F401  # M55-sentinel-crown-d
from . import phantom_sentinel as _phantom_sentinel                # noqa: F401  # M55-sentinel-crown-d
from . import locator_sentinel as _locator_sentinel                # noqa: F401  # M55-sentinel-crown-d
from . import roster_sentinel as _roster_sentinel                  # noqa: F401  # M55-sentinel-crown-d"""

if "M55-sentinel-crown-d" in src:
    print("  already present")
    sys.exit(0)

if anchor not in src:
    print(f"ERROR: anchor not found in {path}", file=sys.stderr)
    sys.exit(1)

open(path, "w").write(src.replace(anchor, anchor + addition))
print("  patched stewardship/__init__.py")
