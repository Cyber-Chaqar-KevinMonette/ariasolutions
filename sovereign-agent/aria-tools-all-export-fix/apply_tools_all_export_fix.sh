#!/usr/bin/env bash
# apply_tools_all_export_fix.sh — export 7 tools that were imported but missing from __all__.
#
# THE BUG (found during a full-system scan, 2026-07-02, widened during L's fix on 2026-07-03):
# `LogPredictionTool`, `ResolvePredictionTool`, `CalibrationLedgerTool` (from calibration_tools.py),
# `HonorLogReadTool`, `HonorLogWriteTool` (from honor_log_tool.py), `SelfPortraitTool`
# (self_portrait_tool.py), and `SessionPortraitTool` (session_portrait_tool.py) are all correctly
# imported into tools/__init__.py but never added to `__all__` — so they're importable directly but
# invisible to any `__all__`-based discovery (e.g. `from sovereign_agent.tools import *`, or any
# registration/introspection code that iterates `tools.__all__`). This is exactly the anchor-integrity
# bug class J's Tier-A scanner harvest is meant to catch generically; this module fixes the 7 real
# instances found and ships the generalized test as the scanner's seed.
#
# Anatomy: guard (cockpit stopped + venv) → backup tools/__init__.py → patch (anchored, idempotent,
# appends before the closing `]`) → py_compile → copy + run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-tools-all-export-fix"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-tools-all-export-fix apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$TOOLS_INIT" ]] || { echo "ERROR: $TOOLS_INIT not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")

MARK = "tools-all-export-fix-d"
if MARK in t:
    print("SKIP: already patched")
else:
    anchor = '    "WholenessTool",  # wholeness-all-d\n]'
    if anchor not in t:
        print(f"ERROR: __all__ closing anchor not found: {anchor!r}", file=sys.stderr)
        sys.exit(1)
    add = (
        '    "WholenessTool",  # wholeness-all-d\n'
        f'    "LogPredictionTool",  # {MARK}\n'
        '    "ResolvePredictionTool",\n'
        '    "CalibrationLedgerTool",\n'
        '    "HonorLogReadTool",\n'
        '    "HonorLogWriteTool",\n'
        '    "SelfPortraitTool",\n'
        '    "SessionPortraitTool",\n'
        ']'
    )
    t = t.replace(anchor, add, 1)
    p.write_text(t, encoding="utf-8")
    print("Patched tools/__init__.py: 7 missing __all__ entries added")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TOOLS_INIT"
echo "  ✓ py_compile clean"

echo "→ Import + export check..."
"$VENV_PY" -c "
from sovereign_agent import tools
for name in ('LogPredictionTool', 'ResolvePredictionTool', 'CalibrationLedgerTool',
             'HonorLogReadTool', 'HonorLogWriteTool', 'SelfPortraitTool', 'SessionPortraitTool'):
    assert name in tools.__all__, f'{name} still missing from __all__'
    assert hasattr(tools, name), f'{name} not importable'
print('  ✓ all 7 tools now in __all__ and importable')
"

cp "$STAGING/tests/test_tools_all_export_fix.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_tools_all_export_fix.py" -q

echo "=== aria-tools-all-export-fix applied. Reversible: backup at $BACKUP_DIR/tools_init.py.bak 💛 ==="
