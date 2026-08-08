"""Patch tools/__init__.py to register M66 institutional impulse tools."""
import sys

path = sys.argv[1]
src = open(path).read()

MARKER = "M66-impulse-d"
if MARKER in src:
    print("  already present")
    sys.exit(0)

IMPORT_BODY = (
    "\nfrom .impulse_tools import (  # M66-impulse-d\n"
    "    InstitutionalImpulseCheckTool,\n"
    "    WedgeCalibratorTool,\n"
    ")\n"
)

ALL_ANCHOR = '"GitCommitReflectTool",'
ALL_BODY = (
    '"InstitutionalImpulseCheckTool",  # M66-impulse-all-d\n'
    '    "WedgeCalibratorTool",\n'
    '    "GitCommitReflectTool",'
)

ALL_DEF = "__all__ = ["
if ALL_DEF not in src:
    print(f"ERROR: __all__ not found in {path}", file=sys.stderr)
    sys.exit(1)

src = src.replace(ALL_DEF, IMPORT_BODY + ALL_DEF)
if ALL_ANCHOR in src:
    src = src.replace(ALL_ANCHOR, ALL_BODY, 1)
else:
    print("WARNING: GitCommitReflectTool anchor not found; skipping __all__ update")

open(path, "w").write(src)
print("  patched tools/__init__.py (M66 impulse tools)")
