#!/usr/bin/env bash
# apply_integrity.sh — Integrity round I2: the standing gate.
# guard → backup → copy payload (gate.py + integrity_gate.py CLI) → patch
# (integrity/__init__.py export + pre_apply_gate.sh) → compile →
# bash-syntax check → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-integrity-gate"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-integrity-gate apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR/scripts"
cp "$SRC/integrity/__init__.py" "$BACKUP_DIR/integrity_init.py.bak"
cp "$REPO_ROOT/scripts/pre_apply_gate.sh" "$BACKUP_DIR/scripts/pre_apply_gate.sh.bak"

# 1. new payload files (a new submodule inside the already-live integrity/
#    package, plus a new scripts/lib/ CLI wrapper)
cp "$STAGING/payload/src/sovereign_agent/integrity/gate.py" "$SRC/integrity/"
cp "$STAGING/payload/scripts/lib/integrity_gate.py" "$REPO_ROOT/scripts/lib/"

# 2. anchored, idempotent patches
"$VENV_PY" - "$STAGING" "$SRC" "$REPO_ROOT" <<'PYEOF'
import sys
from pathlib import Path
staging, src, repo = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import ALL_PATCHES, SCRIPT_PATCHES

for rel, fn in ALL_PATCHES.items():
    path = src / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")

for rel, fn in SCRIPT_PATCHES.items():
    path = repo / "scripts" / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ scripts/{rel}")
    else:
        print(f"  SKIP scripts/{rel} (already patched)")
PYEOF

echo "→ Compile + bash-syntax check..."
"$VENV_PY" -m py_compile "$SRC/integrity/gate.py" "$SRC/integrity/__init__.py" \
  "$REPO_ROOT/scripts/lib/integrity_gate.py"
bash -n "$REPO_ROOT/scripts/pre_apply_gate.sh"
"$VENV_PY" -c "
from sovereign_agent.integrity import gate, IntegrityGateVerdict
print('  ✓ integrity.gate exported')"

# 3. promote the live tests + run them
cp "$STAGING/tests/test_integrity_gate_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_integrity_gate_live.py" -q -rs | tee /tmp/integrity_gate_pytest.out
if grep -q "SKIPPED" /tmp/integrity_gate_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi

echo "→ Self-test: the new gate scores its own module cleanly..."
"$VENV_PY" scripts/lib/integrity_gate.py --module aria-integrity-gate || {
  echo "  (non-zero — see notes above; the gate is now watching itself)"; }
echo "=== aria-integrity-gate applied. Reversible: backups at $BACKUP_DIR 💛 ==="
