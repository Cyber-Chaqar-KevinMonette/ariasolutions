"""Patch stewardship/__init__.py to register ScheduleSentinel."""
import sys

path = sys.argv[1]
src = open(path).read()

# Anchor after the M55 sentinel crown block
anchor = "from . import roster_sentinel as _roster_sentinel                  # noqa: F401  # M55-sentinel-crown-d"
addition = "\nfrom . import schedule_sentinel as _schedule_sentinel              # noqa: F401  # M56-cron-hygiene-d"

if "M56-cron-hygiene-d" in src:
    print("  already present")
    sys.exit(0)

if anchor not in src:
    # Fallback: use atoms-compact as anchor
    anchor = "from . import atoms_compact_sentinel as _atoms_compact_sentinel  # noqa: F401  # atoms-compact-sentinel-d"
    if anchor not in src:
        print(f"ERROR: no anchor found in {path}", file=sys.stderr)
        sys.exit(1)

open(path, "w").write(src.replace(anchor, anchor + addition))
print("  patched stewardship/__init__.py")
