#!/usr/bin/env bash
# apply_read_repair.sh — FABLE II M3: one tolerant reader at every read path.
# guard → backup → copy helper → patch 7 readers → compile → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-read-repair"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-read-repair apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
for rel in checkpoint_chunks/store.py curiosity.py proving_ground/runner.py \
           loose_threads/ledger.py epistemic_ledger/ledger.py \
           stewardship/field_notes.py agent_session.py; do
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp "$SRC/$rel" "$BACKUP_DIR/$rel.bak"
done

# 1. the shared helper
cp "$STAGING/payload/src/sovereign_agent/read_repair.py" "$SRC/read_repair.py"

# 2. anchored, idempotent patches on every hand-rolled reader
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
"$VENV_PY" -m py_compile "$SRC/read_repair.py" \
  "$SRC/checkpoint_chunks/store.py" "$SRC/curiosity.py" \
  "$SRC/proving_ground/runner.py" "$SRC/loose_threads/ledger.py" \
  "$SRC/epistemic_ledger/ledger.py" "$SRC/stewardship/field_notes.py" \
  "$SRC/agent_session.py"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_read_repair_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_read_repair_live.py" -q -rs | tee /tmp/read_repair_pytest.out
if grep -q "SKIPPED" /tmp/read_repair_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
# the suites of every store the patches touched
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_checkpoint_chunks.py" \
  "$REPO_ROOT/tests/test_agent_session.py" -q
echo "=== aria-read-repair applied. Reversible: backups at $BACKUP_DIR 💛 ==="
