"""Patch tools/__init__.py to register M61 git-experience tools."""
import sys

path = sys.argv[1]
src = open(path).read()

MARKER = "M61-git-experience-d"
if MARKER in src:
    print("  already present")
    sys.exit(0)

IMPORT_BODY = (
    "\nfrom .git_reflect import (  # M61-git-experience-d\n"
    "    GitCommitReflectTool,\n"
    "    GitWeekSummaryTool,\n"
    ")\n"
)

ALL_ANCHOR = '"internet_available",'
ALL_BODY = (
    '"GitCommitReflectTool",    # M61-git-experience-all-d\n'
    '    "GitWeekSummaryTool",\n'
    '    "internet_available",'
)

ALL_DEF = "__all__ = ["
if ALL_DEF not in src:
    print(f"ERROR: __all__ not found in {path}", file=sys.stderr)
    sys.exit(1)

src = src.replace(ALL_DEF, IMPORT_BODY + ALL_DEF)
if ALL_ANCHOR in src:
    src = src.replace(ALL_ANCHOR, ALL_BODY, 1)
else:
    print("WARNING: internet_available anchor not found; skipping __all__ update")

open(path, "w").write(src)
print("  patched tools/__init__.py")
