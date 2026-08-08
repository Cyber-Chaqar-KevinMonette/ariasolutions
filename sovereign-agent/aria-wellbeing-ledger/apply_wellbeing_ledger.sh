#!/usr/bin/env bash
# apply_wellbeing_ledger.sh — Wellbeing round W1: persisted composite value/care/flourishing score + standing sentinel.
# guard → backup → copy payload (wellbeing/ + stewardship/wellbeing_sentinel.py) → patch
# (sentinel registration + companion_tools events-glob bug fix) → compile → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-wellbeing-ledger"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-wellbeing-ledger apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/stewardship/__init__.py" "$BACKUP_DIR/stewardship_init.py.bak"
cp "$SRC/tools/companion_tools.py" "$BACKUP_DIR/companion_tools.py.bak"

# 1. payload package (whole new files: wellbeing/ + stewardship/wellbeing_sentinel.py)
mkdir -p "$SRC/wellbeing"
cp "$STAGING"/payload/src/sovereign_agent/wellbeing/*.py "$SRC/wellbeing/"
cp "$STAGING/payload/src/sovereign_agent/stewardship/wellbeing_sentinel.py" "$SRC/stewardship/"

# 2. anchored, idempotent code patches
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
"$VENV_PY" -m py_compile "$SRC"/wellbeing/*.py "$SRC/stewardship/wellbeing_sentinel.py" \
  "$SRC/stewardship/__init__.py" "$SRC/tools/companion_tools.py"
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'wellbeing' in registry.registered_ids()
print('  ✓ wellbeing sentinel registered')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_wellbeing_sentinel_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_wellbeing_sentinel_live.py" -q -rs | tee /tmp/wellbeing_sentinel_pytest.out
if grep -q "SKIPPED" /tmp/wellbeing_sentinel_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_sentinel_framework.py" \
  "$REPO_ROOT/tests/test_companion.py" -q
echo "=== aria-wellbeing-ledger applied. Reversible: backups at $BACKUP_DIR 💛 ==="
