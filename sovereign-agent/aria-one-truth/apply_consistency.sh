#!/usr/bin/env bash
# apply_consistency.sh — FABLE II M1: the one-truth organ (cross-store consistency).
# guard → backup → copy payload → patch (stewardship registry + `sov truth`) → compile → tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-one-truth"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-one-truth apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/stewardship/__init__.py" "$BACKUP_DIR/stewardship_init.py.bak"
cp "$SRC/cli.py" "$BACKUP_DIR/cli.py.bak"

# 1. payload package
mkdir -p "$SRC/consistency"
cp "$STAGING"/payload/src/sovereign_agent/consistency/*.py "$SRC/consistency/"

# 2. anchored, idempotent patches (sentinel registration + `sov truth`)
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import patch_cli, patch_stewardship_init
for path, fn in ((src / "stewardship" / "__init__.py", patch_stewardship_init),
                 (src / "cli.py", patch_cli)):
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {path.name}")
    else:
        print(f"  SKIP {path.name} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC"/consistency/*.py "$SRC/stewardship/__init__.py" "$SRC/cli.py"
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'one-truth' in registry.registered_ids()
print('  ✓ one-truth registered')"

# 3. promote the live tests + run them (plus the sentinel framework suite)
cp "$STAGING/tests/test_one_truth_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_one_truth_live.py" "$REPO_ROOT/tests/test_sentinel_framework.py" -q
echo "=== aria-one-truth applied. Reversible: backups at $BACKUP_DIR 💛 ==="
