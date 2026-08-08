#!/usr/bin/env bash
# apply_quality_gate.sh — Quality round Q2: wire qa/hardening into real gates.
# guard → backup → copy payload (gate.py + quality_gate.py CLI) → patch
# (quality/__init__.py export + pre_apply_gate.sh + safe_apply.sh) → compile
# → bash-syntax check → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-quality-gate"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-quality-gate apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR/scripts"
cp "$SRC/quality/__init__.py" "$BACKUP_DIR/quality_init.py.bak"
cp "$REPO_ROOT/scripts/pre_apply_gate.sh" "$BACKUP_DIR/scripts/pre_apply_gate.sh.bak"
cp "$REPO_ROOT/scripts/safe_apply.sh" "$BACKUP_DIR/scripts/safe_apply.sh.bak"

# 1. new payload files (a new submodule inside the already-live quality/
#    package, plus a new scripts/lib/ CLI wrapper)
cp "$STAGING/payload/src/sovereign_agent/quality/gate.py" "$SRC/quality/"
cp "$STAGING/payload/scripts/lib/quality_gate.py" "$REPO_ROOT/scripts/lib/"

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
"$VENV_PY" -m py_compile "$SRC/quality/gate.py" "$SRC/quality/__init__.py" \
  "$REPO_ROOT/scripts/lib/quality_gate.py"
bash -n "$REPO_ROOT/scripts/pre_apply_gate.sh"
bash -n "$REPO_ROOT/scripts/safe_apply.sh"
"$VENV_PY" -c "
from sovereign_agent.quality import gate, QualityGateVerdict
print('  ✓ quality.gate exported')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_quality_gate_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_quality_gate_live.py" -q -rs | tee /tmp/quality_gate_pytest.out
if grep -q "SKIPPED" /tmp/quality_gate_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi

echo "→ Self-test: the new gate scores its own module cleanly..."
"$VENV_PY" scripts/lib/quality_gate.py --module aria-quality-gate || {
  echo "  (non-zero — see notes above; the gate is now watching itself)"; }
echo "=== aria-quality-gate applied. Reversible: backups at $BACKUP_DIR 💛 ==="
