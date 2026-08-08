#!/usr/bin/env bash
# apply_session_bridge.sh — Stage M83: session_portrait cross-session context tool
#
# What this applies:
#   1. src/sovereign_agent/tools/session_portrait_tool.py — new T0 tool
#   2. tools/__init__.py: import + __all__ entry for SessionPortraitTool
#
# What session_portrait does:
#   Returns a JSON bundle at session start: last session-close atoms,
#   Kevin's care signals, highest-confidence hot atoms, and PEIG state.
#   Maximum continuity across sessions. Call it when a new session begins.
#
# NOTE: Requires M84 (PEIG sentinel) to be applied first for PEIG state.
#       session_portrait degrades gracefully if peig_sentinel is missing.
#
# Reversibility: backups at aria-session-bridge/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-session-bridge"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== M83 Session Bridge Apply Script ==="
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

TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

# ── Backups ───────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR"

# ── Step 1: Copy session_portrait_tool.py ─────────────────────────────────────

DEST_TOOL="$REPO_ROOT/src/sovereign_agent/tools/session_portrait_tool.py"
cp "$STAGING/payload/src/sovereign_agent/tools/session_portrait_tool.py" "$DEST_TOOL"
echo "Copied session_portrait_tool.py → $DEST_TOOL"

# ── Step 2: Patch tools/__init__.py ──────────────────────────────────────────

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path

tools_init = Path(sys.argv[1])
tools = tools_init.read_text()

IMPORT_GUARD  = "# session-bridge-import-d"
IMPORT_ANCHOR = "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d"
ALL_ANCHOR    = '    "PEIGPortraitTool",  # peig-portrait-all-d\n]'
ALL_GUARD     = '"SessionPortraitTool"'

if IMPORT_GUARD in tools:
    print("SKIP: tools/__init__.py import patch already applied")
else:
    if IMPORT_ANCHOR not in tools:
        print(f"ERROR: anchor not found: {IMPORT_ANCHOR!r}", file=sys.stderr)
        sys.exit(1)
    IMPORT_BLOCK = (
        "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d\n"
        "from .session_portrait_tool import SessionPortraitTool  # session-bridge-import-d\n"
    )
    tools = tools.replace(IMPORT_ANCHOR, IMPORT_BLOCK, 1)
    print("Applied tools/__init__.py import patch (SessionPortraitTool)")

if ALL_GUARD not in tools:
    if ALL_ANCHOR not in tools:
        print("WARNING: __all__ anchor not found; skipping __all__ patch")
    else:
        NEW_ALL = (
            '    "PEIGPortraitTool",  # peig-portrait-all-d\n'
            '    "SessionPortraitTool",  # session-bridge-all-d\n'
            ']'
        )
        tools = tools.replace(ALL_ANCHOR, NEW_ALL, 1)
        print("Applied tools/__init__.py __all__ patch (SessionPortraitTool)")
else:
    print("SKIP: SessionPortraitTool already in __all__")

tools_init.write_text(tools)
print("tools/__init__.py written.")
PYEOF

# ── Step 3: Compile check ─────────────────────────────────────────────────────

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$DEST_TOOL" "$TOOLS_INIT"
echo "  ✓ files compile cleanly"

# ── Step 4: Run tests ─────────────────────────────────────────────────────────

echo ""
echo "Running session bridge tests..."
"$VENV_PY" -m pytest aria-session-bridge/tests/test_session_portrait.py -v

echo ""
echo "=== M83 Session Bridge applied successfully ==="
echo "Restart sovereign cockpit to load session_portrait tool."
echo "Try: sov ask 'run session_portrait'"
