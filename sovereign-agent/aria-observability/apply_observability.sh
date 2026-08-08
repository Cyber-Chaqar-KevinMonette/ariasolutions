#!/usr/bin/env bash
# apply_observability.sh — Stage M85b: AriaMetricsTool (confidence-grounding observability)
#
# What this applies:
#   1. src/sovereign_agent/tools/aria_metrics.py     — new file
#   2. tools/__init__.py — import + __all__ entry
#
# Anti-depth-0-mouth: this tool surfaces brain state (atoms, calibration,
# honor, flaws, PEIG) to the language layer so confidence is grounded.
#
# Reversibility: tools/__init__.py backed up.
# Prerequisites: cockpit not running. Run AFTER apply_flaw_catalog.sh.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-observability"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M85b Observability Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo ""

# ── Guards ────────────────────────────────────────────────────────────────────

if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."
    exit 1
fi

# ── Backups ───────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
cp "$INIT" "$BACKUP_DIR/__init__.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR/__init__.py.bak"

# ── Step 1: Copy aria_metrics.py ─────────────────────────────────────────────

cp "$STAGING/payload/src/sovereign_agent/tools/aria_metrics.py" \
   "$REPO_ROOT/src/sovereign_agent/tools/aria_metrics.py"
echo "Copied aria_metrics.py → src/sovereign_agent/tools/aria_metrics.py"

# ── Step 2: Patch tools/__init__.py ──────────────────────────────────────────

"$VENV_PY" - "$INIT" <<'PYEOF'
import sys
from pathlib import Path

init = Path(sys.argv[1])
text = init.read_text()

IMPORT_GUARD = "# observability-import-d"
ALL_GUARD    = "# observability-all-d"

if IMPORT_GUARD in text:
    print("SKIP: aria_metrics import already present")
else:
    # Insert after flaw_tools import if present, otherwise after honor_log import
    ANCHORS = [
        "from .flaw_tools import FlawReadTool, FlawUpdateTool  # flaw-catalog-import-d",
        "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d",
    ]
    anchor = None
    for a in ANCHORS:
        if a in text:
            anchor = a
            break
    if anchor is None:
        print("ERROR: import anchor not found", file=sys.stderr)
        sys.exit(1)
    text = text.replace(
        anchor,
        anchor + "\nfrom .aria_metrics import AriaMetricsTool  # observability-import-d",
        1,
    )
    print("Added aria_metrics import")

if ALL_GUARD in text:
    print("SKIP: aria_metrics __all__ entry already present")
else:
    # Insert after FlawUpdateTool in __all__ if present, else at end before closing ]
    ALL_ANCHORS = [
        '"FlawUpdateTool",',
        '"PEIGPortraitTool",  # peig-portrait-all-d',
    ]
    anchor = None
    for a in ALL_ANCHORS:
        if a in text:
            anchor = a
            break
    if anchor is None:
        print("ERROR: __all__ anchor not found", file=sys.stderr)
        sys.exit(1)
    text = text.replace(
        anchor,
        anchor + '\n    "AriaMetricsTool",  # observability-all-d',
        1,
    )
    print("Added AriaMetricsTool to __all__")

init.write_text(text)
print("tools/__init__.py written.")
PYEOF

# ── Step 3: Compile check ─────────────────────────────────────────────────────

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile \
    "$REPO_ROOT/src/sovereign_agent/tools/aria_metrics.py" \
    "$INIT"
echo "  ✓ compiles"

# ── Step 4: Tests ─────────────────────────────────────────────────────────────

echo ""
echo "→ Running observability tests..."
"$VENV_PY" -m pytest aria-observability/tests/test_aria_metrics.py -v

echo ""
echo "=== M85b Observability applied ==="
echo "New tool: aria_metrics (T0)"
echo ""
echo "When Aria expresses confidence she can now call aria_metrics() and ground it:"
echo '  "847 atoms avg_conf=0.73 · calibration=81%/23 resolved · 0 critical flaws · λ=0.71 committed"'
echo ""
echo "Restart sovereign cockpit to load the new tool."
