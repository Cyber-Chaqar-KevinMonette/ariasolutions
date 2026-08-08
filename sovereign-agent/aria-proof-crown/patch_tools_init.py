"""Patch tools/__init__.py to register M67 proof crown tools."""
import sys

path = sys.argv[1]
src = open(path).read()

MARKER = "M67-proof-crown-d"
if MARKER in src:
    print("  already present")
    sys.exit(0)

IMPORT_BODY = (
    "\nfrom .proof_tools import (  # M67-proof-crown-d\n"
    "    ProofOfValueTool,\n"
    "    ProofHistoryTool,\n"
    "    GivingLedgerTool,\n"
    ")\n"
)

ALL_ANCHOR = '"InstitutionalImpulseCheckTool",'
ALL_BODY = (
    '"ProofOfValueTool",             # M67-proof-crown-all-d\n'
    '    "ProofHistoryTool",\n'
    '    "GivingLedgerTool",\n'
    '    "InstitutionalImpulseCheckTool",'
)

# Fallback if M66 hasn't been applied yet
ALL_ANCHOR_FALLBACK = '"GitCommitReflectTool",'
ALL_BODY_FALLBACK = (
    '"ProofOfValueTool",             # M67-proof-crown-all-d\n'
    '    "ProofHistoryTool",\n'
    '    "GivingLedgerTool",\n'
    '    "GitCommitReflectTool",'
)

ALL_DEF = "__all__ = ["
if ALL_DEF not in src:
    print(f"ERROR: __all__ not found in {path}", file=sys.stderr)
    sys.exit(1)

src = src.replace(ALL_DEF, IMPORT_BODY + ALL_DEF)
if ALL_ANCHOR in src:
    src = src.replace(ALL_ANCHOR, ALL_BODY, 1)
elif ALL_ANCHOR_FALLBACK in src:
    src = src.replace(ALL_ANCHOR_FALLBACK, ALL_BODY_FALLBACK, 1)
    print("  (used fallback anchor — M66 impulse tools not yet registered)")
else:
    print("WARNING: anchor not found; skipping __all__ update")

open(path, "w").write(src)
print("  patched tools/__init__.py (M67 proof crown)")
