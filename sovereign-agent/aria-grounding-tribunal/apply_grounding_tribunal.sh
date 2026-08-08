#!/usr/bin/env bash
# apply_grounding_tribunal.sh — Grounding round G3: standing audit + measured skeptic lens.
# guard → backup → patch (log_to_diagnosis prefix param, skeptic lens,
# grounding_sentinel.py standing phase) → compile → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-grounding-tribunal"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-grounding-tribunal apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/tribunal/tribunal.py" "$BACKUP_DIR/tribunal.py.bak"
cp "$SRC/spectrum/lenses.py" "$BACKUP_DIR/lenses.py.bak"
cp "$SRC/stewardship/grounding_sentinel.py" "$BACKUP_DIR/grounding_sentinel.py.bak"

# anchored, idempotent patches
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
"$VENV_PY" -m py_compile "$SRC/tribunal/tribunal.py" "$SRC/spectrum/lenses.py" \
  "$SRC/stewardship/grounding_sentinel.py"
"$VENV_PY" -c "
from sovereign_agent.tribunal.tribunal import log_to_diagnosis
from sovereign_agent.spectrum.lenses import skeptic
import inspect
assert 'prefix' in inspect.signature(log_to_diagnosis).parameters
print('  ✓ log_to_diagnosis takes prefix; skeptic lens importable')"

# promote the live tests + run them; post-patch this file must run with
# ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_grounding_tribunal_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_grounding_tribunal_live.py" -q -rs | tee /tmp/grounding_tribunal_pytest.out
if grep -q "SKIPPED" /tmp/grounding_tribunal_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_grounding_sentinel_live.py" \
  "$REPO_ROOT/tests/test_grounding_gate_live.py" -q
echo "=== aria-grounding-tribunal applied. Reversible: backups at $BACKUP_DIR 💛 ==="
