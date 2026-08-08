#!/usr/bin/env bash
# apply_quality_tribunal.sh — Quality round Q3: advocates and audits, made standing.
# guard → backup → copy payload (review.py) → patch (log_to_diagnosis bug fix,
# artisan lens, quality/__init__.py export, quality_sentinel.py standing phase)
# → compile → tests (0 skips expected post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-quality-tribunal"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-quality-tribunal apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/tribunal/tribunal.py" "$BACKUP_DIR/tribunal.py.bak"
cp "$SRC/spectrum/lenses.py" "$BACKUP_DIR/lenses.py.bak"
cp "$SRC/quality/__init__.py" "$BACKUP_DIR/quality_init.py.bak"
cp "$SRC/stewardship/quality_sentinel.py" "$BACKUP_DIR/quality_sentinel.py.bak"

# 1. new payload file (a new submodule inside the already-live quality/ package)
cp "$STAGING/payload/src/sovereign_agent/quality/review.py" "$SRC/quality/"

# 2. anchored, idempotent patches
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
  "$SRC/quality/__init__.py" "$SRC/quality/review.py" \
  "$SRC/stewardship/quality_sentinel.py"
"$VENV_PY" -c "
from sovereign_agent.quality import build_review_proposal
from sovereign_agent.spectrum.lenses import artisan
print('  ✓ build_review_proposal exported; artisan lens importable')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_quality_tribunal_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_quality_tribunal_live.py" -q -rs | tee /tmp/quality_tribunal_pytest.out
if grep -q "SKIPPED" /tmp/quality_tribunal_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_quality_sentinel_live.py" \
  "$REPO_ROOT/tests/test_quality_gate_live.py" -q
echo "=== aria-quality-tribunal applied. Reversible: backups at $BACKUP_DIR 💛 ==="
