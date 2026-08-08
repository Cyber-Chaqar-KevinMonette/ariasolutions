"""Patch stewardship/__init__.py to register atoms_compact_sentinel."""
import sys

path = sys.argv[1]
src = open(path).read()
anchor = "from . import telemetry_sentinel as _telemetry_sentinel  # noqa: F401  # telemetry-sentinel-d"
addition = "\nfrom . import atoms_compact_sentinel as _atoms_compact_sentinel  # noqa: F401  # atoms-compact-sentinel-d"

if "atoms-compact-sentinel-d" in src:
    print("  already present")
    sys.exit(0)
if anchor not in src:
    print(f"ERROR: anchor not found in {path}", file=sys.stderr)
    sys.exit(1)
open(path, "w").write(src.replace(anchor, anchor + addition))
print("  patched stewardship/__init__.py")
