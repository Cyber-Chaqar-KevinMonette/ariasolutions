#!/usr/bin/env bash
# apply_integrity.sh — Integrity round I4: the "honest" stance.
# guard → backup → patch (stances.py + session_bridge.py + observatory.py,
# all in-place edits to already-live files — no new payload) → compile →
# tests (0 skips/failures expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-integrity-modes"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-integrity-modes apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/modes_crown/stances.py" "$BACKUP_DIR/stances.py.bak"
cp "$SRC/session_bridge.py" "$BACKUP_DIR/session_bridge.py.bak"
cp "$SRC/modes_crown/observatory.py" "$BACKUP_DIR/observatory.py.bak"

# anchored, idempotent patches (no new payload files this round)
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
from sovereign_agent.modes_crown.stances import SAFE_STANCES, integrity_gate_clear
assert 'honest' in SAFE_STANCES
print('  ✓ honest stance registered; integrity_gate_clear importable')"

# promote the live tests + run them; post-patch this file must run with
# ZERO skips/failures (the failures only exist pre-apply)
cp "$STAGING/tests/test_integrity_modes_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_integrity_modes_live.py" -q -rs

echo "=== aria-integrity-modes applied. Reversible: backups at $BACKUP_DIR 💛 ==="
