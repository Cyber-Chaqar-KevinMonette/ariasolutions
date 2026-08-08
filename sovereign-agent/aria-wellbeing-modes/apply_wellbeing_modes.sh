#!/usr/bin/env bash
# apply_wellbeing_modes.sh — Wellbeing round W4: a stance for deliberate reflection.
# guard → backup → patch (stances.py, session_bridge.py, observatory.py)
# → compile → tests (0 skips expected post-patch). Patch-only — no new
# payload files.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-wellbeing-modes"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-wellbeing-modes apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/modes_crown/stances.py" "$BACKUP_DIR/stances.py.bak"
cp "$SRC/session_bridge.py" "$BACKUP_DIR/session_bridge.py.bak"
cp "$SRC/modes_crown/observatory.py" "$BACKUP_DIR/observatory.py.bak"

# anchored, idempotent patches
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
"$VENV_PY" -m py_compile "$SRC/modes_crown/stances.py" "$SRC/session_bridge.py" \
  "$SRC/modes_crown/observatory.py"
"$VENV_PY" -c "
from sovereign_agent.modes_crown.stances import SAFE_STANCES, wellbeing_gate_clear
assert 'reflecting' in SAFE_STANCES
print('  ✓ reflecting stance wired; wellbeing_gate_clear importable')"

# promote the live tests + run them; post-patch this file must run with
# ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_wellbeing_modes_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_wellbeing_modes_live.py" -q -rs | tee /tmp/wellbeing_modes_pytest.out
if grep -q "SKIPPED" /tmp/wellbeing_modes_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_wellbeing_sentinel_live.py" \
  "$REPO_ROOT/tests/test_wellbeing_gate_live.py" \
  "$REPO_ROOT/tests/test_wellbeing_tribunal_live.py" \
  "$REPO_ROOT/tests/test_grounding_modes_live.py" \
  "$REPO_ROOT/tests/test_quality_modes_live.py" -q
echo "=== aria-wellbeing-modes applied. Reversible: backups at $BACKUP_DIR 💛 ==="
