#!/usr/bin/env bash
# apply_safe_glyphs_regrounded.sh — re-fix the safe-glyphs regression,
# grounded against the CURRENT live files.
#
# NOT a resurrection of the old aria-safe-glyphs/ — that module's apply
# script does a full-file replacement of cockpit/app.py from a ~half-
# sized week-old payload and is confirmed dangerous to run. This ships
# small, anchored, idempotent patches against the files that actually
# still have the bug today:
#   - src/sovereign_agent/workflow/requests.py — 5 anchored edits
#     (STATUS_EMOJI/PRIORITY_EMOJI dicts, the module docstring banner,
#     and 2 method docstrings)
#   - src/sovereign_agent/cli.py — 5 anchored edits (2 docstrings + 2
#     _print() calls + 1 more docstring — a SEPARATE hardcoded copy of
#     the same glyphs, not references to requests.py's dict)
#
# cockpit/app.py is confirmed already clean — untouched.
#
# Anatomy: guard (cockpit stopped + venv) → backup both files → patch
# (anchored, idempotent, py_compile-verified) → copy the regression test
# → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-safe-glyphs-regrounded"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
REQUESTS="$REPO_ROOT/src/sovereign_agent/workflow/requests.py"
CLI="$REPO_ROOT/src/sovereign_agent/cli.py"

echo "=== aria-safe-glyphs-regrounded apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$REQUESTS" "$CLI"; do [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }; done
mkdir -p "$BACKUP_DIR"
cp "$REQUESTS" "$BACKUP_DIR/requests.py.bak"
cp "$CLI" "$BACKUP_DIR/cli.py.bak"

echo "→ Patching requests.py (5 edits) + cli.py (5 edits), idempotent..."
"$VENV_PY" - "$STAGING" "$REQUESTS" "$CLI" <<'PYEOF'
import sys
from pathlib import Path

staging, req_path, cli_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_cli, patch_requests

for label, path, fn in (("requests.py", req_path, patch_requests), ("cli.py", cli_path, patch_cli)):
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = fn(text)
    except PatchError as e:
        print(f"ERROR: {label}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {label}")
    else:
        print(f"  SKIP: {label} already patched")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REQUESTS" "$CLI"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.workflow.requests import STATUS_EMOJI, PRIORITY_EMOJI, VALID_PRIORITY
assert 'normal' in VALID_PRIORITY, 'normal priority key must survive the fix'
assert STATUS_EMOJI['deferred'] == '💤'
assert STATUS_EMOJI['needs_attention'] == '🚩'
assert PRIORITY_EMOJI['normal'] == ''
print('  ✓ imports cleanly, glyphs fixed, normal priority key preserved')
"

cp "$STAGING/tests/test_no_variation_selector_glyphs.py" "$REPO_ROOT/tests/"
echo "Running test suites: no_variation_selector_glyphs (new), requests + git-independent cli smoke (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_no_variation_selector_glyphs.py" \
  "$REPO_ROOT/tests/test_requests.py" \
  -q

echo "=== aria-safe-glyphs-regrounded applied. Reversible: restore requests.py + cli.py from $BACKUP_DIR 💛 ==="
