#!/usr/bin/env bash
# apply_people_health.sh — People-Health round PH1+PH2: offline health
# tracking, consent-gated, scoped to the principal + explicitly-consented
# others.
#
# guard → backup → copy payload (sql/015_people_health.sql,
# mem_channels/people_health.py, tools/health_record_tool.py) → patch
# (tools/__init__.py registration) → compile → copy tests → run tests.
# Reversible: backups under aria-people-health/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-people-health"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-people-health apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/tools/__init__.py" "$BACKUP_DIR/tools_init.py.bak"

# 1. copy payload: a new migration, a new channel, a new tool
cp "$STAGING/payload/sql/015_people_health.sql" "$REPO_ROOT/sql/"
cp "$STAGING/payload/src/sovereign_agent/mem_channels/people_health.py" "$SRC/mem_channels/"
cp "$STAGING/payload/src/sovereign_agent/tools/health_record_tool.py" "$SRC/tools/"

# 2. anchored, idempotent patch (tool registration)
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import ALL_PATCHES

for rel, fn in ALL_PATCHES.items():
    path = src / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC/mem_channels/people_health.py" "$SRC/tools/health_record_tool.py" \
  "$SRC/tools/__init__.py"
"$VENV_PY" -c "
from sovereign_agent.tools import RecordHealthFactTool
print('  ✓ RecordHealthFactTool exported')"

# 3. promote + run tests
cp "$STAGING/tests/test_people_health.py" "$STAGING/tests/test_health_record_tool.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_people_health.py" "$REPO_ROOT/tests/test_health_record_tool.py" -q

echo "=== aria-people-health applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "→ Still needed: PH3 (retrieval privacy filter, doctor.py channel count,"
echo "  and the third-party-consent canon clause — STOP AND ASK before touching mos_canon.py)."
