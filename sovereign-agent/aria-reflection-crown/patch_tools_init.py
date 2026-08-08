"""Patch tools/__init__.py to register M59 reflection-crown tools."""
import sys

path = sys.argv[1]
src = open(path).read()

MARKER = "M59-reflection-crown-d"
if MARKER in src:
    print("  already present")
    sys.exit(0)

IMPORT_ANCHOR = '"internet_available",'
# Fallback: find __all__ end and insert before it
IMPORT_BODY = (
    "from .reflection_tools import (  # M59-reflection-crown-d\n"
    "    WeeklyReflectionTool,\n"
    "    ReflectionHistoryTool,\n"
    ")\n"
)

# Insert import at end of imports block (before __all__)
ALL_ANCHOR = '"internet_available",'
ALL_BODY = (
    '"WeeklyReflectionTool",    # M59-reflection-crown-all-d\n'
    '    "ReflectionHistoryTool",\n'
    '    "internet_available",'
)

# Find "from .workflow_tools import" and add after the closing paren
WORKFLOW_IMPORT = "from .workflow_tools import (  # workflow-wire-import-d\n    WorkflowCreateTool, WorkflowStepTool, WorkflowStatusTool,\n)"
if WORKFLOW_IMPORT in src:
    src = src.replace(WORKFLOW_IMPORT, WORKFLOW_IMPORT + "\n" + IMPORT_BODY)
else:
    # Fallback: look for "__all__" and insert before it
    ALL_DEF = "__all__ = ["
    if ALL_DEF in src:
        src = src.replace(ALL_DEF, IMPORT_BODY + ALL_DEF)
    else:
        print(f"ERROR: no import anchor found in {path}", file=sys.stderr)
        sys.exit(1)

if ALL_ANCHOR in src:
    src = src.replace(ALL_ANCHOR, ALL_BODY, 1)
else:
    print("WARNING: __all__ anchor not found; skipping __all__ update")

open(path, "w").write(src)
print("  patched tools/__init__.py")
