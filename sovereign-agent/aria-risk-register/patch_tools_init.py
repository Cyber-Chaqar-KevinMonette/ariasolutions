"""Patch tools/__init__.py to register RiskRegisterReadTool + RiskRegisterProposeTool."""
import sys

path = sys.argv[1]
src = open(path).read()

MARKER = "M57-risk-register-d"
if MARKER in src:
    print("  already present")
    sys.exit(0)

IMPORT_ANCHOR = (
    "from .atoms_compact_tool import (  # atoms-compact-import-d\n"
    "    AtomsCompactPreviewTool,\n"
    "    AtomsCompactTool,\n"
    "    AtomsCompactStatusTool,\n"
    ")"
)
IMPORT_ADDITION = (
    "\nfrom .risk_tools import (  # M57-risk-register-d\n"
    "    RiskRegisterReadTool,\n"
    "    RiskRegisterProposeTool,\n"
    ")"
)

ALL_ANCHOR = '"internet_available",'
ALL_ADDITION = (
    '"RiskRegisterReadTool",  # M57-risk-register-all-d\n'
    '    "RiskRegisterProposeTool",\n'
    '    "internet_available",'
)

if IMPORT_ANCHOR not in src:
    print(f"ERROR: import anchor not found in {path}", file=sys.stderr)
    sys.exit(1)

if ALL_ANCHOR not in src:
    print(f"ERROR: __all__ anchor not found in {path}", file=sys.stderr)
    sys.exit(1)

src = src.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADDITION)
src = src.replace(ALL_ANCHOR, ALL_ADDITION)
open(path, "w").write(src)
print("  patched tools/__init__.py")
