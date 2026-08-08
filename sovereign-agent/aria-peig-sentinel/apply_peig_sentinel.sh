#!/usr/bin/env bash
# apply_peig_sentinel.sh — Stage M84: PEIG state sentinel + peig_portrait tool
#
# What this applies:
#   1. src/sovereign_agent/stewardship/peig_sentinel.py  — new sentinel
#   2. src/sovereign_agent/tools/peig_portrait_tool.py  — new T0 tool
#   3. stewardship/__init__.py: import peig_sentinel (triggers @register_sentinel)
#   4. tools/__init__.py: import + __all__ entry for PEIGPortraitTool
#
# PEIG: Kevin's computational design language — Potential · Energy ·
# Identity · Curvature + λ coherence gate. Read-only; purely observational.
# Safety: no heal(), no self-modification, λ is advisory only.
#
# Reversibility: backups at aria-peig-sentinel/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-peig-sentinel"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== M84 PEIG Sentinel Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo "Backup dir: $BACKUP_DIR"
echo ""

# ── Guards ────────────────────────────────────────────────────────────────────

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first, then re-run."
    exit 1
fi

if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

STEWARDSHIP_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

if [[ ! -f "$STEWARDSHIP_INIT" ]]; then
    echo "ERROR: stewardship/__init__.py not found"
    exit 1
fi

# ── Backups ───────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
cp "$STEWARDSHIP_INIT" "$BACKUP_DIR/stewardship_init.py.bak"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
echo "Backed up __init__.py files → $BACKUP_DIR"

# ── Step 1: Copy source files ─────────────────────────────────────────────────

DEST_SENTINEL="$REPO_ROOT/src/sovereign_agent/stewardship/peig_sentinel.py"
DEST_TOOL="$REPO_ROOT/src/sovereign_agent/tools/peig_portrait_tool.py"

cp "$STAGING/payload/src/sovereign_agent/stewardship/peig_sentinel.py" "$DEST_SENTINEL"
echo "Copied peig_sentinel.py → $DEST_SENTINEL"

cp "$STAGING/payload/src/sovereign_agent/tools/peig_portrait_tool.py" "$DEST_TOOL"
echo "Copied peig_portrait_tool.py → $DEST_TOOL"

# ── Steps 2 & 3: Patch __init__.py files via Python ──────────────────────────

"$VENV_PY" - "$STEWARDSHIP_INIT" "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path

stewardship_init = Path(sys.argv[1])
tools_init = Path(sys.argv[2])

# ── Patch stewardship/__init__.py — register sentinel on import ───────────────
STEW_GUARD  = "# peig-sentinel-import-d"
STEW_ANCHOR = "from .honor import HonorLedger, HonorNote"

stew = stewardship_init.read_text()
if STEW_GUARD in stew:
    print("SKIP: stewardship/__init__.py patch already applied")
else:
    if STEW_ANCHOR not in stew:
        print(f"ERROR: stewardship anchor not found: {STEW_ANCHOR!r}", file=sys.stderr)
        sys.exit(1)
    STEW_BLOCK = (
        "from .honor import HonorLedger, HonorNote\n"
        "from . import peig_sentinel  # peig-sentinel-import-d — triggers @register_sentinel\n"
    )
    stew = stew.replace(STEW_ANCHOR, STEW_BLOCK, 1)
    stewardship_init.write_text(stew)
    print("Applied stewardship/__init__.py patch (peig_sentinel import)")

# ── Patch tools/__init__.py — import PEIGPortraitTool ────────────────────────
TOOLS_GUARD   = "# peig-portrait-import-d"
TOOLS_ANCHOR  = "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d"
ALL_ANCHOR    = '    "LineageTool",  # lineage-all-d\n]'

tools = tools_init.read_text()

if TOOLS_GUARD in tools:
    print("SKIP: tools/__init__.py import patch already applied")
else:
    if TOOLS_ANCHOR not in tools:
        print(f"ERROR: tools anchor not found: {TOOLS_ANCHOR!r}", file=sys.stderr)
        sys.exit(1)
    TOOLS_BLOCK = (
        "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d\n"
        "from .peig_portrait_tool import PEIGPortraitTool  # peig-portrait-import-d\n"
    )
    tools = tools.replace(TOOLS_ANCHOR, TOOLS_BLOCK, 1)
    print("Applied tools/__init__.py import patch (PEIGPortraitTool)")

# ── Add to __all__ ────────────────────────────────────────────────────────────
ALL_GUARD = '"PEIGPortraitTool"'
if ALL_GUARD not in tools:
    if ALL_ANCHOR not in tools:
        print("WARNING: __all__ anchor not found; skipping __all__ patch")
    else:
        NEW_ALL = (
            '    "LineageTool",  # lineage-all-d\n'
            '    "PEIGPortraitTool",  # peig-portrait-all-d\n'
            ']'
        )
        tools = tools.replace(ALL_ANCHOR, NEW_ALL, 1)
        print("Applied tools/__init__.py __all__ patch (PEIGPortraitTool)")
else:
    print("SKIP: PEIGPortraitTool already in __all__")

tools_init.write_text(tools)
print("tools/__init__.py written.")
PYEOF

# ── Step 4: Compile check ─────────────────────────────────────────────────────

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$DEST_SENTINEL" "$DEST_TOOL" "$STEWARDSHIP_INIT" "$TOOLS_INIT"
echo "  ✓ all files compile cleanly"

# ── Step 5: Run tests ─────────────────────────────────────────────────────────

echo ""
echo "Running PEIG sentinel tests..."
"$VENV_PY" -m pytest aria-peig-sentinel/tests/test_peig_sentinel.py -v

echo ""
echo "=== M84 PEIG Sentinel applied successfully ==="
echo "Restart sovereign cockpit to load peig_portrait and the PEIG sentinel."
echo "Try: sov ask 'run peig_portrait'"
