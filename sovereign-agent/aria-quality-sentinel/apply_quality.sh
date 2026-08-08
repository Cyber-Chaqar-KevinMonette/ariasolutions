#!/usr/bin/env bash
# apply_quality.sh — Quality round Q1: the persisted quality ledger + standing sentinel.
# guard → backup → copy payload → patch (sentinel registration + worker-latch persistence
# + GOD_TIER_CRITERIA.md doc sync) → compile → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-quality-sentinel"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-quality-sentinel apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/stewardship/__init__.py" "$BACKUP_DIR/stewardship_init.py.bak"
cp "$SRC/cockpit/app.py" "$BACKUP_DIR/app.py.bak"
cp "$REPO_ROOT/GOD_TIER_CRITERIA.md" "$BACKUP_DIR/GOD_TIER_CRITERIA.md.bak"

# 1. payload package (whole new files: quality/ + stewardship/quality_sentinel.py)
mkdir -p "$SRC/quality"
cp "$STAGING"/payload/src/sovereign_agent/quality/*.py "$SRC/quality/"
cp "$STAGING/payload/src/sovereign_agent/stewardship/quality_sentinel.py" "$SRC/stewardship/"

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

# 3. doc sync
"$VENV_PY" - "$STAGING" "$REPO_ROOT" <<'PYEOF'
import sys
from pathlib import Path
staging, repo = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import DOC_PATCHES
for rel, fn in DOC_PATCHES.items():
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC"/quality/*.py "$SRC/stewardship/quality_sentinel.py" \
  "$SRC/stewardship/__init__.py" "$SRC/cockpit/app.py"
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'quality' in registry.registered_ids()
print('  ✓ quality sentinel registered')"

# 4. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_quality_sentinel_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_quality_sentinel_live.py" -q -rs | tee /tmp/quality_sentinel_pytest.out
if grep -q "SKIPPED" /tmp/quality_sentinel_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_sentinel_framework.py" -q
echo "=== aria-quality-sentinel applied. Reversible: backups at $BACKUP_DIR 💛 ==="
