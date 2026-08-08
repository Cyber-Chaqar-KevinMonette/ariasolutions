#!/usr/bin/env bash
# apply_honor_calibration.sh — Apply M79: calibration + honor log tools
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-honor-calibration"

echo "=== M79: Honor & Calibration Tools ==="

# 1. Copy tool files
echo "→ Copying calibration_tools.py and honor_log_tool.py..."
cp "$STAGING/payload/src/sovereign_agent/tools/calibration_tools.py" \
   "$REPO/src/sovereign_agent/tools/calibration_tools.py"
cp "$STAGING/payload/src/sovereign_agent/tools/honor_log_tool.py" \
   "$REPO/src/sovereign_agent/tools/honor_log_tool.py"

# 2. Patch tools/__init__.py
INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if ! grep -q "calibration-import-d" "$INIT"; then
    echo "→ Patching tools/__init__.py..."
    cd "$REPO"
    .venv/bin/python - <<'PYEOF'
from pathlib import Path
init = Path("src/sovereign_agent/tools/__init__.py")
content = init.read_text()

IMPORTS = (
    '\nfrom .calibration_tools import ('
    'LogPredictionTool, ResolvePredictionTool, CalibrationLedgerTool'
    ')  # calibration-import-d\n'
    'from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d\n'
)
ALL_ENTRIES = (
    '    "LogPredictionTool",  # calibration-all-d\n'
    '    "ResolvePredictionTool",\n'
    '    "CalibrationLedgerTool",\n'
    '    "HonorLogReadTool",  # honor-log-all-d\n'
    '    "HonorLogWriteTool",\n'
)

content = content.replace('\n__all__ = [', IMPORTS + '\n__all__ = [')

content = content.replace(
    '    "internet_available",\n    "reset_internet_cache",\n]',
    '    "internet_available",\n    "reset_internet_cache",\n'
    + ''.join(ALL_ENTRIES) + ']'
)

init.write_text(content)
print("  tools/__init__.py patched")
PYEOF
else
    echo "→ tools/__init__.py already patched, skipping"
fi

# 3. Copy and run tests
echo "→ Copying tests..."
cp "$STAGING/tests/test_calibration_tools.py" "$REPO/tests/test_calibration_tools.py"
cp "$STAGING/tests/test_honor_log_tool.py"    "$REPO/tests/test_honor_log_tool.py"

echo "→ Running calibration tests..."
cd "$REPO"
.venv/bin/python -m pytest tests/test_calibration_tools.py -v --tb=short

echo "→ Running honor log tests..."
.venv/bin/python -m pytest tests/test_honor_log_tool.py -v --tb=short

echo ""
echo "=== M79 complete ==="
echo "New tools: log_prediction (T1), resolve_prediction (T1), calibration_ledger (T0)"
echo "New tools: honor_log_read (T0), honor_log_write (T1)"
echo "New tests: 8 calibration + 7 honor log = 15 total"
