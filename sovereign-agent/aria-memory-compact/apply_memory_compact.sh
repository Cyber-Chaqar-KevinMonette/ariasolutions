#!/usr/bin/env bash
# apply_memory_compact.sh — FABLE II M2: bounded growth with dignity.
# guard → backup → copy payload → patch (sentinel + `sov compact` + chunk cold fallback) → compile → tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-memory-compact"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-memory-compact apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/stewardship/__init__.py" "$BACKUP_DIR/stewardship_init.py.bak"
cp "$SRC/cli.py" "$BACKUP_DIR/cli.py.bak"
cp "$SRC/checkpoint_chunks/store.py" "$BACKUP_DIR/chunk_store.py.bak"

# 1. payload package
mkdir -p "$SRC/memory_compact"
cp "$STAGING"/payload/src/sovereign_agent/memory_compact/*.py "$SRC/memory_compact/"

# 2. anchored, idempotent patches
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import patch_chunk_store, patch_cli, patch_stewardship_init
for path, fn in ((src / "stewardship" / "__init__.py", patch_stewardship_init),
                 (src / "cli.py", patch_cli),
                 (src / "checkpoint_chunks" / "store.py", patch_chunk_store)):
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {path}")
    else:
        print(f"  SKIP {path} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC"/memory_compact/*.py "$SRC/stewardship/__init__.py" "$SRC/cli.py" "$SRC/checkpoint_chunks/store.py"
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'memory-compact' in registry.registered_ids()
print('  ✓ memory-compact registered')"

# 3. promote the live tests + run them (plus the chunk suite the patch touches)
cp "$STAGING/tests/test_memory_compact_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_memory_compact_live.py" "$REPO_ROOT/tests/test_checkpoint_chunks.py" "$REPO_ROOT/tests/test_sentinel_framework.py" -q
echo "=== aria-memory-compact applied. Reversible: backups at $BACKUP_DIR 💛 ==="
