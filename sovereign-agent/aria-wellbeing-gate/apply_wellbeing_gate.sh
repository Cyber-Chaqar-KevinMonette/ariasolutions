#!/usr/bin/env bash
# apply_wellbeing_gate.sh — Wellbeing round W2: persistence at the source, real teeth.
# guard → backup → copy payload (gate.py) → patch (wellbeing/__init__.py export
# + companion_tools.py ValueReportTool persistence hook) → compile → tests
# (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-wellbeing-gate"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-wellbeing-gate apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/wellbeing/__init__.py" "$BACKUP_DIR/wellbeing_init.py.bak"
cp "$SRC/tools/companion_tools.py" "$BACKUP_DIR/companion_tools.py.bak"

# 1. new payload file (a new submodule inside the already-live wellbeing/
#    package)
cp "$STAGING/payload/src/sovereign_agent/wellbeing/gate.py" "$SRC/wellbeing/"

# 2. anchored, idempotent patches
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
"$VENV_PY" -m py_compile "$SRC/wellbeing/gate.py" "$SRC/wellbeing/__init__.py" \
  "$SRC/tools/companion_tools.py"
"$VENV_PY" -c "
from sovereign_agent.wellbeing import gate, WellbeingGateVerdict
print('  ✓ wellbeing.gate exported')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_wellbeing_gate_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_wellbeing_gate_live.py" -q -rs | tee /tmp/wellbeing_gate_pytest.out
if grep -q "SKIPPED" /tmp/wellbeing_gate_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_companion.py" \
  "$REPO_ROOT/tests/test_wellbeing_sentinel_live.py" -q
echo "=== aria-wellbeing-gate applied. Reversible: backups at $BACKUP_DIR 💛 ==="
