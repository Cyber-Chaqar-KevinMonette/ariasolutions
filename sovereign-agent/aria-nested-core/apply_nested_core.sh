#!/usr/bin/env bash
# apply_nested_core.sh — install Workstream E: nest the Holographic BitNet's
# conditioning lever inside the Superposition Processor's amplitude
# amplification.
#
# Ships:
#   - src/sovereign_agent/nonclassical_supreme/superpose.py — 2 anchored,
#     idempotent patches: evolve() gets two new OPTIONAL kwargs
#     (holo_weight=0.0 default — an exact no-op — and conditioner=None),
#     plus two new functions (holographic_bias(), the nesting mechanism;
#     evaluate_holographic_nesting(), the honest EXPAI evidence gate).
#     NOT a full-file replace.
#
# No new file is added — this patches the one existing module the plan
# named. torch is imported lazily INSIDE holographic_bias() only, never at
# module level, so nonclassical_supreme stays torch-free/CPU-only by
# default (its entire stated purpose).
#
# Anatomy: guard (cockpit stopped + venv) → backup superpose.py → patch
# (anchored, idempotent, py_compile-verified) → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-nested-core"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SUPERPOSE="$REPO_ROOT/src/sovereign_agent/nonclassical_supreme/superpose.py"

echo "=== aria-nested-core apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$SUPERPOSE" ]] || { echo "ERROR: $SUPERPOSE not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SUPERPOSE" "$BACKUP_DIR/superpose.py.bak"

echo "→ Patching superpose.py (2 anchored edits, idempotent)..."
"$VENV_PY" - "$STAGING" "$SUPERPOSE" <<'PYEOF'
import sys
from pathlib import Path

staging, sp_path = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_superpose

text = sp_path.read_text(encoding="utf-8")
try:
    new_text, changed = patch_superpose(text)
except PatchError as e:
    print(f"ERROR: superpose.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed:
    sp_path.write_text(new_text, encoding="utf-8")
    print("  ✓ patched superpose.py")
else:
    print("  SKIP: superpose.py already patched")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SUPERPOSE"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.nonclassical_supreme.superpose import evolve, holographic_bias, evaluate_holographic_nesting, process
print('  ✓ imports cleanly')
print('  ✓ baseline process() still works:', process('blue sky', ['red apple', 'blue sky'])['result'])
"

# NOTE: promote test_nested_core_live.py, NOT test_nested_core.py. The
# latter uses a shadow-copy-and-patch mechanism needed only for pre-apply
# verification; promoting it caused real regressions elsewhere this
# session — see aria-security-strip-wire's README for the full story.
cp "$STAGING/tests/test_nested_core_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: nested_core_live (new), nonclassical_supreme (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_nested_core_live.py" \
  "$REPO_ROOT/tests/test_nonclassical_supreme.py" \
  -q

echo "=== aria-nested-core applied. Reversible: restore superpose.py from $BACKUP_DIR 💛 ==="
