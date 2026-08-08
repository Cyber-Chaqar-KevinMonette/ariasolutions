"""Patch tools/__init__.py to register M58 hypothesis-close tools."""
import sys

path = sys.argv[1]
src = open(path).read()

MARKER = "M58-hypothesis-close-d"
if MARKER in src:
    print("  already present")
    sys.exit(0)

IMPORT_ANCHOR = (
    "from .risk_tools import (  # M57-risk-register-d\n"
    "    RiskRegisterReadTool,\n"
    "    RiskRegisterProposeTool,\n"
    ")"
)
IMPORT_ADDITION = (
    "\nfrom .hypothesis_close import (  # M58-hypothesis-close-d\n"
    "    HypothesisQueueTool,\n"
    "    HypothesisSynthesisTool,\n"
    "    HypothesisArchiveTool,\n"
    ")"
)

ALL_ANCHOR = '"RiskRegisterReadTool",  # M57-risk-register-all-d'
ALL_ADDITION = (
    '"HypothesisQueueTool",      # M58-hypothesis-close-all-d\n'
    '    "HypothesisSynthesisTool",\n'
    '    "HypothesisArchiveTool",\n'
    '    "RiskRegisterReadTool",  # M57-risk-register-all-d'
)

if IMPORT_ANCHOR not in src:
    # Fallback: use atoms-compact anchor
    IMPORT_ANCHOR = (
        "from .atoms_compact_tool import (  # atoms-compact-import-d\n"
        "    AtomsCompactPreviewTool,\n"
        "    AtomsCompactTool,\n"
        "    AtomsCompactStatusTool,\n"
        ")"
    )
    IMPORT_ADDITION = (
        "\nfrom .hypothesis_close import (  # M58-hypothesis-close-d\n"
        "    HypothesisQueueTool,\n"
        "    HypothesisSynthesisTool,\n"
        "    HypothesisArchiveTool,\n"
        ")"
        + IMPORT_ADDITION
    )
    if IMPORT_ANCHOR not in src:
        print(f"ERROR: no import anchor found in {path}", file=sys.stderr)
        sys.exit(1)

if ALL_ANCHOR not in src:
    # Fallback
    ALL_ANCHOR = '"internet_available",'
    ALL_ADDITION = (
        '"HypothesisQueueTool",      # M58-hypothesis-close-all-d\n'
        '    "HypothesisSynthesisTool",\n'
        '    "HypothesisArchiveTool",\n'
        '    "internet_available",'
    )

src = src.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADDITION)
src = src.replace(ALL_ANCHOR, ALL_ADDITION, 1)
open(path, "w").write(src)
print("  patched tools/__init__.py")
