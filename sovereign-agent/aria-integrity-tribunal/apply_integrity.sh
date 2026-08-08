#!/usr/bin/env bash
# apply_integrity.sh — Integrity round I3: standing sentinel + witness
# lens measured-data override.
# guard → backup → copy payload (new sentinel file) → patch
# (spectrum/lenses.py witness override + stewardship/__init__.py
# registration) → compile → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-integrity-tribunal"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-integrity-tribunal apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/spectrum/lenses.py" "$BACKUP_DIR/lenses.py.bak"
cp "$SRC/stewardship/__init__.py" "$BACKUP_DIR/stewardship_init.py.bak"

# 1. new payload file (a new sentinel inside the already-live stewardship/ package)
cp "$STAGING/payload/src/sovereign_agent/stewardship/self_integrity_sentinel.py" "$SRC/stewardship/"

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
"$VENV_PY" -m py_compile "$SRC/stewardship/self_integrity_sentinel.py" \
  "$SRC/spectrum/lenses.py" "$SRC/stewardship/__init__.py"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips/failures (the one failure only exists pre-apply)
cp "$STAGING/tests/test_self_integrity_sentinel_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_self_integrity_sentinel_live.py" -q -rs

echo "=== aria-integrity-tribunal applied. Reversible: backups at $BACKUP_DIR 💛 ==="
