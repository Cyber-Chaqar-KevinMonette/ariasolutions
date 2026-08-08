#!/usr/bin/env bash
# apply_db_armor.sh — install Gym #4: uniform SQLite hardening.
#
# atoms.db/events.db already carry the proven pragma block (db.py:19-22);
# this applies the same busy_timeout=5000 (+ synchronous=NORMAL, + WAL
# where missing) to the five stores that lacked it: palace.py, shards.py,
# persistence/store.py (the weakest — had NEITHER per-connection pragma),
# feedback/feedback.py (via one new _connect() helper), aegis/bitemporal.py.
# busy_timeout is per-connection, which is why every patch lands at a
# connect site, not in schema SQL.
#
# Anatomy: guard → backup all 5 files → patch (anchored, idempotent,
# py_compile-verified) → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-db-armor"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-db-armor apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
for f in palace.py shards.py persistence/store.py feedback/feedback.py aegis/bitemporal.py; do
  [[ -f "$SRC/$f" ]] || { echo "ERROR: $SRC/$f not found."; exit 1; }
  cp "$SRC/$f" "$BACKUP_DIR/$(basename "$f").bak"
done

echo "→ Patching 5 stores (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path

staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import (
    PatchError,
    patch_aegis, patch_feedback, patch_palace, patch_persistence, patch_shards,
)

targets = [
    ("palace.py", src / "palace.py", patch_palace),
    ("shards.py", src / "shards.py", patch_shards),
    ("persistence/store.py", src / "persistence" / "store.py", patch_persistence),
    ("feedback/feedback.py", src / "feedback" / "feedback.py", patch_feedback),
    ("aegis/bitemporal.py", src / "aegis" / "bitemporal.py", patch_aegis),
]
for name, path, fn in targets:
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = fn(text)
    except PatchError as e:
        print(f"ERROR: {name}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {name}")
    else:
        print(f"  SKIP: {name} already patched")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$SRC/palace.py" "$SRC/shards.py" "$SRC/persistence/store.py" \
  "$SRC/feedback/feedback.py" "$SRC/aegis/bitemporal.py"
echo "  ✓ py_compile clean"

cp "$STAGING/tests/test_db_armor_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: db_armor_live (new) + pre-existing suites touching the patched stores..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_db_armor_live.py" \
  "$REPO_ROOT/tests/test_palace_write.py" \
  "$REPO_ROOT/tests/test_workflow_wire.py" \
  -q

echo "=== aria-db-armor applied. Reversible: restore the 5 files from $BACKUP_DIR 💛 ==="
