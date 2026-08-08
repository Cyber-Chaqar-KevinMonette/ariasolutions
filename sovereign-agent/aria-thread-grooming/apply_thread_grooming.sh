#!/usr/bin/env bash
# apply_thread_grooming.sh — FABLE II M5: the loose-threads first grooming.
# guard → backup → patch (scanner idioms + lease action + bridge wire) → compile → tests (0 skips).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-thread-grooming"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-thread-grooming apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
for rel in loose_threads/scanner.py autonomy/session.py session_bridge.py; do
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp "$SRC/$rel" "$BACKUP_DIR/$rel.bak"
done

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
"$VENV_PY" -m py_compile "$SRC/loose_threads/scanner.py" "$SRC/autonomy/session.py" "$SRC/session_bridge.py"

cp "$STAGING/tests/test_thread_grooming_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_thread_grooming_live.py" -q -rs | tee /tmp/thread_grooming_pytest.out
if grep -q "SKIPPED" /tmp/thread_grooming_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_loose_threads_live.py" "$REPO_ROOT/tests/test_session_bridge_live.py" -q
echo "=== aria-thread-grooming applied. Reversible: backups at $BACKUP_DIR 💛 ==="
