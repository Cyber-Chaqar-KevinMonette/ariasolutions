"""Patch tools/__init__.py to add atoms_compact_tool imports and __all__ entries."""
import sys

path = sys.argv[1]
src = open(path).read()

# --- Step 1: add import block after notify-crown imports ---
import_anchor = "from .notify_tools import (  # notify-crown-import-d\n    NotifyTool,\n    NotifyStatusTool,\n)"
import_addition = """
from .atoms_compact_tool import (  # atoms-compact-import-d
    AtomsCompactPreviewTool,
    AtomsCompactTool,
    AtomsCompactStatusTool,
)"""

if "atoms-compact-import-d" not in src:
    if import_anchor not in src:
        print(f"ERROR: import anchor not found in {path}", file=sys.stderr)
        sys.exit(1)
    src = src.replace(import_anchor, import_anchor + import_addition, 1)

# --- Step 2: add to __all__ ---
all_anchor = '"NotifyTool",'
all_addition = """
    "AtomsCompactPreviewTool",  # atoms-compact-all-d
    "AtomsCompactTool",
    "AtomsCompactStatusTool","""

if "atoms-compact-all-d" not in src:
    if all_anchor not in src:
        print(f"ERROR: __all__ anchor not found in {path}", file=sys.stderr)
        sys.exit(1)
    src = src.replace(all_anchor, all_anchor + all_addition, 1)

open(path, "w").write(src)
print("  patched tools/__init__.py")
